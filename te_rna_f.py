#===================================================
def find_intersect(bam_remaining, chr_bed, flat_bed_pos, flat_bed_ind):
#===================================================

    """
    This function finds the intersection between a bam file and a flattened bed file of insertion positions, 
    and returns the UMIs, bed indeces, and bam indeces of the reads that overlap.

    Inputs:
    bam_remaining: bam file of reads that have not yet been counted
    chr_bed: bed file of insertions on a given chromosome
    flat_bed_pos: flattened vector of 5' insertion positions across all insertions in chr_bed
    flat_bed_ind: flattened vector of indeces for each region that maps it back onto the original chr bed file

    Outputs:
    umi: vector of UMIs that overlap with flattened bed
    bedind: vector of indeces in original bed file where umi_v reads have aligned
    ind: vector of pd row indeces of original bam file where reads have aligned

    """
    import numpy as np

    _int = np.intersect1d(bam_remaining['Start'].values, flat_bed_pos, return_indices=True)  #Find indeces (in the bam file of 5' aligned reads only) of reads whose tss overlaps with flattened bed vector
    umi = bam_remaining['UMI'].iloc[_int[1]].values #vector of UMIs that overlap with flattened bed
    bedind = flat_bed_ind[_int[2]] #vector of indeces in original bed file where umi_v reads have aligned
    ind = bam_remaining.index[_int[1]].values #vector of indeces of original bam file where reads have aligned
    assert len(umi) == len(bedind), 'Bam and bed slices not the same length'

    return(umi, bedind, ind)
