#!/usr/bin/env python

#
# Copyright 2015, Daehwan Kim <infphilo@gmail.com>
#
# This file is part of HISAT 2.
#
# HISAT 2 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HISAT 2 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HISAT 2.  If not, see <http://www.gnu.org/licenses/>.
#

from sys import stdout, stderr, exit
from collections import defaultdict, Counter
from argparse import ArgumentParser, FileType
from math import exp

"""
"""
def reverse_complement(seq):
    result = ""
    for nt in seq:
        base = nt
        if nt == 'A':
            base = 'T'
        elif nt == 'a':
            base = 't'
        elif nt == 'C':
            base = 'G'
        elif nt == 'c':
            base = 'g'
        elif nt == 'G':
            base = 'C'
        elif nt == 'g':
            base = 'c'
        elif nt == 'T':
            base = 'A'
        elif nt == 't':
            base = 'a'
        
        result = base + result
    
    return result


"""
"""
def read_genome(genome_file):
    chr_dic = {}
    
    chr_name, sequence = "", ""
    for line in genome_file:
        if line[0] == ">":
            if chr_name and sequence:
                chr_dic[chr_name] = sequence
            
            chr_name = line[1:-1]
            sequence = ""
        else:
            sequence += line[:-1]

    if chr_name and sequence:
        chr_dic[chr_name] = sequence
    
    return chr_dic


"""
"""
def read_transcript(gtf_file):
    genes = defaultdict(list)
    transcripts = {}

    # Parse valid exon lines from the GTF file into a dict by transcript_id
    for line in gtf_file:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '#' in line:
            line = line.split('#')[0].strip()
        try:
            chrom, source, feature, left, right, score, \
                strand, frame, values = line.split('\t')
        except ValueError:
            continue
        # Zero-based offset
        left, right = int(left) - 1, int(right) - 1
        if feature != 'exon' or left >= right:
            continue

        values_dict = {}
        for attr in values.split(';')[:-1]:
            attr, _, val = attr.strip().partition(' ')
            values_dict[attr] = val.strip('"')

        if 'gene_id' not in values_dict or \
                'transcript_id' not in values_dict:
            continue

        transcript_id = values_dict['transcript_id']
        if transcript_id not in transcripts:
            transcripts[transcript_id] = [chrom, strand, [[left, right]]]
            genes[values_dict['gene_id']].append(transcript_id)
        else:
            transcripts[transcript_id][2].append([left, right])

    # Sort exons and merge where separating introns are <=5 bps
    for tran, [chr, strand, exons] in transcripts.items():
            exons.sort()
            tmp_exons = [exons[0]]
            for i in range(1, len(exons)):
                if exons[i][0] - tmp_exons[-1][1] <= 5:
                    tmp_exons[-1][1] = exons[i][1]
                else:
                    tmp_exons.append(exons[i])
            transcripts[tran] = [chr, strand, tmp_exons]

    return genes, transcripts
    

"""
"""
def read_snp(snp_file):
    snps = []
    for line in snp_file:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        try:
            snpID, type, chr, pos, data = line.split('\t')
        except ValueError:
            continue

        assert type in ["single", "deletion", "insertion"]
        if type == "deletion":
            data = int(data)
        snps.append([snpID, type, chr, int(pos), data])

    return snps


"""
"""
def sanity_check_input(genome_seq, genes, transcripts, snps):
    num_canon_ss, num_ss = 0, 0
    for transcript, [chr, strand, exons] in transcripts.items():
        if len(exons) <= 1:
            continue
        if chr not in genome_seq:
            continue
        chr_seq = genome_seq[chr]
        for i in range(len(exons) - 1):
            left1, right1 = exons[i]
            assert left1 < right1
            left2, right2 = exons[i+1]
            assert left2 < right2
            assert left1 < left2 and right1 < right2
            donor = chr_seq[right1+1:right1+3]
            acceptor = chr_seq[left2-2:left2]
            if strand == "-":
                donor, acceptor = reverse_complement(acceptor), reverse_complement(donor)
            if donor == "GT" and acceptor == "AG":
                num_canon_ss += 1
            num_ss += 1

    print >> stdout, "GT/AG splice sites: {}/{} ({:.2%})".format(num_canon_ss, num_ss, (float(num_canon_ss) / num_ss))

    num_alt_single, num_single = 0, 0
    for snp in snps:
        snpID, type, chr, pos, data = snp
        if type != "single":
            continue
        if chr not in genome_seq:
            continue
        chr_seq = genome_seq[chr]
        assert pos < len(chr_seq)
        if chr_seq[pos] != data:
            num_alt_single += 1
        num_single += 1

    print >> stdout, "Alternative bases: {}/{} ({:.2%})".format(num_alt_single, num_single, (float(num_alt_single) / num_single))


"""
"""
def generate_expr_profile(expr_profile_type, num_transcripts = 10000):
    # Modelling and simulating generic RNA-Seq experiments with the flux simulator
    # http://nar.oxfordjournals.org/content/suppl/2012/06/29/gks666.DC1/nar-02667-n-2011-File002.pdf
    def calc_expr(x, a):
        x, a = float(x), float(a)
        b = a
        k = -0.6
        return (x**k) * exp(x/a * (x/b)**2)
    
    expr_profile = [0.0] * num_transcripts
    for i in range(len(expr_profile)):
        if expr_profile_type == "flux":
            expr_profile[i] = calc_expr(i + 1, num_transcripts)
        elif expr_profile_type == "constant":
            expr_profile[i] = 1.0
        else:
            assert False

    expr_sum = sum(expr_profile)
    expr_profile = [expr_profile[i] / expr_sum for i in range(len(expr_profile))]
    assert abs(sum(expr_profile) - 1.0) < 0.001
    return expr_profile


"""
"""
def simulate_reads(genome_file, gtf_file, snp_file, \
                       rna, paired_end, read_length, frag_length, \
                       num_frag, expr_profile_type, sam_file, \
                       sanity_check, verbose):

    genome_seq = read_genome(genome_file)
    genes, transcripts = read_transcript(gtf_file)
    snps = read_snp(snp_file)

    if sanity_check:
        sanity_check_input(genome_seq, genes, transcripts, snps)

    expr_profile = generate_expr_profile(expr_profile_type)
    print expr_profile[:10]


    """
    # Print some stats if asked
    if verbose:
        exon_lengths, intron_lengths, trans_lengths = \
            Counter(), Counter(), Counter()
        for chrom, strand, exons in trans.values():
            tran_len = 0
            for i, exon in enumerate(exons):
                exon_len = exon[1]-exon[0]+1
                exon_lengths[exon_len] += 1
                tran_len += exon_len
                if i == 0:
                    continue
                intron_lengths[exon[0] - exons[i-1][1]] += 1
            trans_lengths[tran_len] += 1

        print('exons: {}, exon avg. length: {:d}'.format(
                sum(exon_lengths.values()),
                sum(exon_lengths.elements())/sum(exon_lengths.values())),
              file=stderr)
    """


if __name__ == '__main__':
    parser = ArgumentParser(
        description='Simulate reads from GENOME (fasta) and GTF files')
    parser.add_argument('genome_file',
                        nargs='?',
                        type=FileType('r'),
                        help='input GENOME file')
    parser.add_argument('gtf_file',
                        nargs='?',
                        type=FileType('r'),
                        help='input GTF file')
    parser.add_argument('snp_file',
                        nargs='?',
                        type=FileType('r'),
                        help='input SNP file')
    parser.add_argument('-d', '--dna',
                        dest='rna',
                        action='store_false',
                        default=True,
                        help='DNA-seq reads (default: RNA-seq reads)')
    parser.add_argument('--single-end',
                        dest='paired_end',
                        action='store_false',
                        default=True,
                        help='single-end reads (default: paired-end reads)')
    parser.add_argument('-r', '--read-length',
                        dest='read_length',
                        action='store',
                        type=int,
                        default=100,
                        help='read length (default: 100)')
    parser.add_argument('-f', '--fragment-length',
                        dest='frag_length',
                        action='store',
                        type=int,
                        default=250,
                        help='fragment length (default: 250)')
    parser.add_argument('-n', '--num-fragment',
                        dest='num_frag',
                        action='store',
                        type=int,
                        default=1000000,
                        help='number of fragments (default: 1000000)')
    parser.add_argument('-e', '--expr-profile',
                        dest='expr_profile',
                        action='store',
                        type=str,
                        default='flux',
                        help='expression profile: flux or constant (default: flux)')
    parser.add_argument('-s', '--sam-file',
                        dest='sam_file',
                        type=FileType('w'),
                        default=stdout,
                        help='output SAM file (use "-" for stdin)')
    parser.add_argument('--sanity-check',
                        dest='sanity_check',
                        action='store_true',
                        help='sanity check')
    parser.add_argument('-v', '--verbose',
                        dest='verbose',
                        action='store_true',
                        help='also print some statistics to stderr')
    parser.add_argument('--version', 
                        action='version',
                        version='%(prog)s 2.0.0-alpha')
    args = parser.parse_args()
    if not args.gtf_file:
        parser.print_help()
        exit(1)
    simulate_reads(args.genome_file, args.gtf_file, args.snp_file, \
                       args.rna, args.paired_end, args.read_length, args.frag_length, \
                       args.num_frag, args.expr_profile, \
                       args.sam_file, args.sanity_check, args.verbose)
