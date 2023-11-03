import numpy as np

#===================================================
def find_intersect(bam_remaining, flat_bed_pos, flat_bed_ind):
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
    

    _int = np.intersect1d(bam_remaining['Start'].values, flat_bed_pos, return_indices=True)  #Find indeces (in the bam file of 5' aligned reads only) of reads whose tss overlaps with flattened bed vector
    umi = bam_remaining['UMI'].iloc[_int[1]].values #vector of UMIs that overlap with flattened bed
    bedind = flat_bed_ind[_int[2]] #vector of indeces in original bed file where umi_v reads have aligned
    ind = bam_remaining.index[_int[1]].values #vector of indeces of original bam file where reads have aligned
    assert len(umi) == len(bedind), 'Bam and bed slices not the same length'

    return(umi, bedind, ind)



#=========================================
def five_prime_align(chr_bam, chr_bed,  count_df, bam_ind):
#=========================================
    """
    This function takes a bam file of reads and a bed file of TE insertions and
    filters out reads that do not overlap with the 5' portion of the TE insertion. 
    The output is a csv file of counts at each TE insertion. Multi-read UMIs have
    normalised counts by dividing by the number of multi-reads for each UMI.

    Inputs:
        chr_bam: bam file of reads aligned to a single chromosome
        chr_bed: bed file of TE insertions on a single chromosome
        count_df: dataframe of counts at each TE insertion
        bam_ind: vector of indeces from original full bam file of reads that have aligned to 5' ends at their tss

    Outputs:
        count_df: dataframe of counts at each TE insertion
        bam_ind: vector of indeces from original full bam file of reads that have aligned to 5' ends at their tss
    """

    import pandas as pd
    import os
    import sys
    import te_rna_f as te
    sys.path.insert(1, '/cndd3/dburrows/CODE/admin_tools/')
    from admin_tools import admin_functions as adm

    # Filter out reads that do not overlap with 5' portion of insertion

    #Generate flattened vector of 5' insertion positions and their indeces
    all_bed_pos = np.asarray([(np.arange(chr_bed['Start'].values[i], chr_bed['End'].values[i]+1), np.full(chr_bed['End'].values[i]+1 - chr_bed['Start'].values[i],i)) for i in range(len(chr_bed))]) #list of all bed positions for each insertion and their indeces
    assert len(all_bed_pos) == len(chr_bed), 'Not all bed positions accounted for'

    flat_bed_pos = np.ravel(np.asarray(all_bed_pos)[:,0]) # flattened vector of all 5' regions across all insertions
    flat_bed_ind = np.ravel(np.asarray(all_bed_pos)[:,1]) # flattened vector of indeces for each region that maps it back onto the original bed file
    assert len(flat_bed_pos) == len(flat_bed_ind), 'Bed position and index vectors not the same length'

    # get BAM file of final aligning reads
    bam_bool = np.in1d(chr_bam['Start'].values, flat_bed_pos) #Boolean of indeces of reads whose tss overlaps with bed files
    bam_final = chr_bam[bam_bool] #Final bam reads that have aligned to 5' ends


    bam_remaining = bam_final

    #Mop up reads and their locations until none remaining
    umi_v, bedind_v, ind_v = [],[],[]
    #Loop until all reads have been accounted for
    while len(bam_remaining) > 0:
        umi, bedind, ind = te.find_intersect(bam_remaining, flat_bed_pos, flat_bed_ind)
        umi_v = np.append(umi_v, umi) #UMIs of reads that have aligned to 5' ends
        bedind_v=np.append(bedind_v,bedind) #Indeces of chr_bed insertions where each UMI has aligned
        ind_v = np.append(ind_v, ind) # pandas row indeces of chr_bam file where each UMI comes from
        bam_remaining = bam_remaining.drop(ind) #Drop reads that have already been counted
    if len(bedind_v) > 0: bedind_v = bedind_v.astype(int)
    assert len(bam_final) == len(umi_v) == len(bedind_v) == len(ind_v), 'Not all reads accounted for'
    assert len(np.unique(ind_v)) == len(ind_v), 'Some reads counted twice'
    #append index vector for creation of bam file of reads that have aligned to 5' ends
    if len(bedind_v) > 0: bam_ind = np.append(bam_ind, ind_v.astype(int))

    #Sort by UMI
    sort_umi, sort_bedind = adm.sort_2list(umi_v, bedind_v)

    #Get counts!
    #==============================================================================
    slice_umi, slice_count= np.unique(sort_umi, return_counts=True) #Find unique multi-UMIs and their counts
    counts_v = np.ones(len(sort_umi))

    #Loop over multi-UMIs
    for s in slice_umi[np.where(slice_count > 1)]:
        sort_umi_ind = np.ravel(np.argwhere(np.in1d(sort_umi,s))) #Indeces of sorted UMI list where current multi-UMI is found

        #Assert
        #Check that all identified multi-UMIs have at least 2 reads
        if len(sort_umi_ind) < 2:
            assert False, 'Identified multi-UMIs have only 1 or 0 reads'

        assert sum(counts_v[sort_umi_ind] != 1) == 0, str(x) #'This multi-UMIs has already been counted'
        counts_v[sort_umi_ind] = 1/len(sort_umi_ind) 

    assert len(sort_umi) ==  len(sort_bedind) == counts_v.shape[0], 'Output vectors wrong shape'

    curr_df = chr_bed.iloc[sort_bedind]
    curr_df['Count'] = counts_v 
    count_df = pd.concat([count_df, curr_df]) #Add them to the count matrix
    return(count_df, bam_ind)


#assertion -> check that only spliced reads are removed
#================================================================
def splice_check(path):
#================================================================
    """
    This function checks that only spliced reads are removed from the bam file.
    Inputs:
        path: path to directory containing bam files
    Outputs:
        None
    """

    import pysam as sam
    
    full = sam.AlignmentFile(path+'/5pfilt-tss.bam', 'rb')
    nosplice = sam.AlignmentFile(path+'/5pfilt-tss_nosplice.bam', 'rb')
    
    cig_list = []
    full_count=0
    for x,read in enumerate(full):
        cig_list.append(read.cigarstring)
        full_count+=1
    n_splice = len([i for i in cig_list if 'N' in i])
    print(str(np.round(len([i for i in cig_list if 'N' in i])/len(cig_list) * 100,decimals=5)) + ' % of reads are spliced')

    cig_list = []
    filt_count=0
    for x,read in enumerate(nosplice):
        cig_list.append(read.cigarstring)
        filt_count+=1
    n_splice_filt = len([i for i in cig_list if 'N' in i])

    assert n_splice_filt == 0, 'some spliced reads still remain in 5pfilt-tss_nosplice.bam'
    assert full_count - n_splice == filt_count, 'not all spliced reads accounted for'
    print('all spliced reads removed')
    
    


#================================================================
def pysam_subset(file_path):
#================================================================
    """
    This function subsets the columns of the bam file to only include the columns of interest for ATEM filtering.

    """
    import pysam
    import pandas as pd
    fin = pysam.AlignmentFile(file_path, 'rb')
    out = {'Chromosome':[], 'Start': [], 'End': [], 'Strand': [], 'Flag': [] }
    for x,read in enumerate(fin):
        out['Chromosome'].append(read.reference_name)
        out['Start'].append(read.reference_start)
        out['End'].append(read.reference_end)
        out['Flag'].append(read.flag)
        if read.is_forward == True:
            out['Strand'].append('+')
        elif read.is_reverse == True:
            out['Strand'].append('-')
    out = pd.DataFrame(out)
    return(out)

#================================================================
def load_ATEM_family(ATEM_path, te, mode):
#================================================================
    """
    This function loads an ATEM counts table and returns a vector of mean CPMs for each element or family.

    Inputs:
        ATEM_path: path to ATEM counts table
        te: vector of elements or families to get mean CPMs for
        mode (str): CPM or Counts

    Outputs:
        cpm_v: vector of total CPMs/Counts for each element or family

    """
    import pandas as pd

    #Load ATEM counts table
    count_mat = pd.read_csv(ATEM_path, sep="\t", header=0) 
    count_sum = count_mat.groupby('gene_id').sum() #Sum counts for each element

    #Calculate summed CPMs for each element
    cpm_v =[]
    for i in range(len(te)):
        if sum(te[i] == count_sum.index) > 0: cpm_v.append(count_sum[te[i] == count_sum.index][mode].values[0])
        else: cpm_v.append(0)
    return cpm_v
    

#==============================================================================
def rmsk_filter(df, promoter_cutoff, length_cutoff, n_start, n_end, family):
#==============================================================================
    """
        This function filters the rmsk file for non-truncated insertions and those still containing the promoter, 
        returning plus and minus strands - it also changes the genome insertion size to just match the promoter overlap region
        - but the length column still reports the full length. 
    
        Inputs:
            df (dataframe): dataframe of full repeat masker file
            promoter_cutoff (int): maximum number of bps from the 5' end of the consensus promoter that can be missing to be included
            length_cutoff (int): minimum length of the full insertion to be included
            n_start (int): number of bps upstream of 5' end that reads can map to
            n_end (int): number of bps downstream of 5' end that reads can map to
            family (str): TE family
            
        Outputs:
            plusfilt (dataframe): full length, promoter containing insertions on plus strand
            minusfilt (dataframe): full length, promoter containing insertions on minus strand

    """

    #Split strands
    plus = df[df['strand'] == '+'] [df['repFamily']==family]
    minus = df[df['strand'] == '-'] [df['repFamily']==family]
    assert len(plus) + len(minus) == sum(df['repFamily']==family), 'Some insertions not assigned to +/- strands'

    #Filter for promoter and length
    plus_filt = plus[plus['repStart'] < promoter_cutoff][plus['length'] > length_cutoff]
    minus_filt = minus[minus['repLeft'] < promoter_cutoff] [minus['length'] > length_cutoff]

    #SANITY CHECK
    assert sum(plus_filt ["length"] > length_cutoff) == len(plus_filt), 'Lengths are incorrectly filtered'
    assert sum(plus_filt ["repStart"] < promoter_cutoff) == len(plus_filt), 'Promoter portions are too short'
    assert sum(minus_filt ["length"] > length_cutoff) == len(minus_filt), 'Lengths are incorrectly filtered'
    assert sum(minus_filt ["repLeft"] < promoter_cutoff) == len(minus_filt), 'Promoter portions are too short'

    #Replace start/end of insertion with overlap range that reads must overlap with
    plus_filt['full_End'] = plus_filt['genoEnd']
    plus_filt['full_Start'] = plus_filt['genoStart']
    plus_filt['genoEnd'] = plus_filt['genoStart'] + n_end
    plus_filt['genoStart'] = plus_filt['genoStart'] - n_start

    minus_filt['full_End'] = minus_filt['genoEnd']
    minus_filt['full_Start'] = minus_filt['genoStart']
    minus_filt['genoStart'] = minus_filt['genoEnd'] - n_end
    minus_filt['genoEnd'] = minus_filt['genoEnd'] + n_start

    te_plus = plus_filt[['genoName', 'genoStart', 'genoEnd', 'strand', 'repName', 'repFamily', 'repClass', 'length', 'full_Start', 'full_End']]
    te_minus = minus_filt[['genoName', 'genoStart', 'genoEnd', 'strand', 'repName','repFamily', 'repClass', 'length', 'full_Start', 'full_End']]
    
    
    te_plus = te_plus.rename(columns={'genoName': 'Chromosome', 'genoStart':'Start', 
                                      'genoEnd':'End', 'strand':'Strand', 'repName':'gene_id', 
                                      'repFamily':'family_id', 'repClass': 'class_id'})
    te_minus = te_minus.rename(columns={'genoName': 'Chromosome', 'genoStart':'Start', 
                                      'genoEnd':'End', 'strand':'Strand', 'repName':'gene_id', 
                                      'repFamily':'family_id', 'repClass': 'class_id'})
    
    te_plus.loc[te_plus['Start'] < 0,'Start'] = 0
    te_plus.loc[te_plus['End'] < 0,'End'] = 0

    te_minus.loc[te_minus['Start'] < 0,'Start'] = 0
    te_minus.loc[te_minus['End'] < 0,'End'] = 0

   

    #SANITY CHECK
    assert sum(te_plus["Strand"] == "+") == len(te_plus), 'Some non plus strands assigned to plus bed'
    assert sum(te_minus["Strand"] == "-") == len(te_minus), 'Some non minus strands assigned to minus bed'

    return(te_plus, te_minus)

#==============================================================================
def calculate_age(milli_div, subsitution_rate=2.2):
#==============================================================================
    
    p = milli_div / 1000  # The milliDiv column in the `rmsk.txt` file.
    p_part = (4 / 3) * p
    jc_dist = -0.75 * (np.log(1 - p_part))
    (jc_dist * 100) / (subsitution_rate * 2 * 100) * 1000
    return jc_dist

#=========================================
def read_rmsk(filename: str):
#=========================================

    import gzip
    from math import log
    import pandas as pd

    # read first line to check if it is a valid rmsk file
    if filename.endswith(".gz"):
        with gzip.open(filename) as f:
            line = f.readline()
    else:
        with open(filename) as f:
            line = f.readline()

        assert (
            line
            == "   SW  perc perc perc  query      position in query           matching       repeat              position in  repeat\n"
        ), "Not a valid rmsk file"

    # setup converter functions
    strand_conv = lambda x: "-" if x == "C" else "+"
    coord_conv = lambda x: int(x.rstrip(")").lstrip("("))
    perc_conv = lambda x: float(x) * 10

    convs = {
        "milliDiv": perc_conv,
        "milliDel": perc_conv,
        "milliIns": perc_conv,
        "genoLeft": coord_conv,
        "strand": strand_conv,
        "repStart": coord_conv,
        "repLeft": coord_conv,
    }

    # read the rmsk file
    df = pd.read_csv(
        filename,
        skiprows=3,
        delim_whitespace=True,
        names=[
            "swScore",
            "milliDiv",
            "milliDel",
            "milliIns",
            "genoName",
            "genoStart",
            "genoEnd",
            "genoLeft",
            "strand",
            "repName",
            "repClassFamily",
            "repStart",
            "repEnd",
            "repLeft",
            "id",
        ],
        converters=convs,
    )

    # split repClassFamily into repClass and repFamily on /
    df[["repClass", "repFamily"]] = df["repClassFamily"].str.split("/", expand=True)
    df.drop("repClassFamily", axis=1, inplace=True)

    # calculate length of each repeat
    df["length"] = df.apply(
        lambda x: x["repEnd"] - x["repLeft"]
        if x["strand"] == "-"
        else x["repEnd"] - x["repStart"],
        axis=1,
    )

    # calculate age of each repeat
    df["age"] = df["milliDiv"].apply(calculate_age)

    return df


#========================
def spear_adjp(df, age, alpha):
#========================
    """
    This functon calculates spearman's correlation for each subfamily and applies FDR correction.

    Input:
    df: dataframe with subfamily expression values
    age: age of the samples

    Output:
    spear_age_res: dataframe with spearman's correlation, p-value and adjusted p-value for each subfamily
    """


    import numpy as np
    import pandas as pd
    import scipy.stats as stats
    import mne 
    res = stats.spearmanr(np.reshape(age, (1,len(age))), np.asarray(df), axis=1)
    stat = res.statistic[1:,0]
    pval = res.pvalue[1:,0]

    sig_v, adj_p_vals = mne.stats.fdr_correction(pval, alpha, 'indep') #Use Benjamini hochberg FDR test 

    spear_age_res = pd.DataFrame({'stat':stat, 'pval':pval, 'adj_pval':adj_p_vals}, index=df.index.values)
    spear_age_res['geneid'] = spear_age_res.index
    return(spear_age_res)


#======================================== 
def te_group_coarse(df, meta, name):
#======================================== 

    """
    This function takes in a dataframe of TE counts and metadata for specific donors, and returns a list of mean CPM values and age for each donor.

    Input:
    df: dataframe of TE counts
    meta: dataframe of metadata
    name: TE family name (L1, Alu or SVA)

    Output:
    cpm_v: list of mean CPM values for each donor
    age_v: list of ages for each donor
    """
    if name != 'L1' and name != 'Alu' and name != 'SVA':
        print('Error: TE family not recognised, must be L1, Alu or SVA')
        return()

    ind = [x for x,i in enumerate(df.index) if name in i]#l1 ind
    cpm_v = [np.mean(df.iloc[ind][i])for i in meta['sample'].values]
    age_v = meta['AGEYEARS'].values

    return(cpm_v, age_v)


#======================================== 
def te_group_el(df, meta, name):
#======================================== 

    """
    This function takes in a dataframe of TE counts and metadata for specific donors, and returns a dataframe of CPM values for each TE subfamily, and age for each donor.

    Input:
    df: dataframe of TE counts
    meta: dataframe of metadata
    name: TE family name (L1, Alu or SVA)

    Output:
    cpm_df: dataframe of CPM values for each TE subfamily
    age_v: list of ages for each donor
    """
    import pandas as pd

    
    if name != 'L1' and name != 'Alu' and name != 'SVA':
        print('Error: TE family not recognised, must be L1, Alu or SVA')
        return()

    ind = [x for x,i in enumerate(df.index) if name in i]#l1 ind
    cpm_v = [df.iloc[ind][i] for i in meta['sample'].values]
    cpm_df = pd.DataFrame(cpm_v).T
    age_v = meta['AGEYEARS'].values

    return(cpm_df, age_v)


#===============================
def multimap_stats(path):
#===============================

    """
    This function takes in a path to a bam file and returns the number of reads that map to multiple locations versus uniquely as a dataframe.

    Parameters
    ----------
    path : str
        Path to bam file

    Returns
    -------
    df : pandas dataframe
        Dataframe with number of reads that map to multiple locations versus uniquely
    """
    import pysam
    import pandas as pd
    fin = pysam.AlignmentFile(path, 'rb')
    count=0
    test=[]
    for x,read in enumerate(fin):
        test = np.append(test,read.query_name)
        count+=1

    unq = np.unique(test, return_counts=True)
    n_unq = sum(unq[1] == 1)
    n_multi = sum(unq[1] > 1)
    perc_unq = (n_unq/(n_unq+n_multi))*100
    perc_unq_all_reads = (n_unq / (len(test)))*100

    df = pd.DataFrame({'n_unique': [n_unq], 'multi': [n_multi], 'perc_unq_vs_multi_singlereads': [perc_unq], 'perc_unq_vs_multi_allreads': [perc_unq_all_reads]})
    return(df)


#===============================
def paired_test(s1, s2):
#===============================

    """
    This function takes in two vectors of data, tests for normality and then performs appropriate parameteric
     (independent t-test) or non-parametric test (MWU).

    Parameters
    ----------
    s1 : vector of data
    s2 : vector of data

    Returns
    -------
    stat : t-statistic
    p : p-value
    """
    from scipy.stats import shapiro
    from scipy.stats import mannwhitneyu
    from scipy.stats import ttest_ind
    stat1, p1 = shapiro(s1)
    stat2, p2 = shapiro(s2)
    if p1 < 0.05 or p2 < 0.05:
        #non-parametric indendent t test
        stat, p = mannwhitneyu(s1, s2)
    else:
        #parametric independent t test
        stat, p = ttest_ind(s1, s2)

    return(stat,p)

#==========================================================
def inf_paired_comp(class_l, cell_l, period_l, group_df, mode):
#==========================================================
    """
    This function takes in a dataframe of RNA counts, and lists of gene classes, celltypes and age groups to loop over
    , and groups all data into a dataframe of p values for comparisons with Infancy groups. 

    Inputs:
        class_l: list of gene classes to loop over
        cell_l: list of celltypes to loop over
        period_l: list of age groups to loop over
        group_df: dataframe of RNA counts
        mode (str): string indicating coarse or granular TE mode

    Outputs:
        comp_df: dataframe of p values for comparisons with Infancy groups
    """
    import pandas as pd

    comp_df = {'celltype':[], 'Class':[], 'Comparison':[], 'p value':[], 'padj_sig': [], 'statistic':[]}
    for cl in class_l:
        for cell in cell_l:
            for p in period_l:
                #get data
                curr_df = group_df[group_df['Class'] == cl]
                curr_df = curr_df[curr_df['celltype'] == cell]
                per_df = curr_df[curr_df['period'] == p]
                #get data for comparison
                comp_df['celltype'].append(cell)
                comp_df['Class'].append(cl)
                comp_df['Comparison'].append('infancy' + '_' + p)
                comp_df['p value'].append(paired_test(curr_df['RNA'][curr_df['period'] == 'Infancy'], per_df['RNA'].values)[1])
                comp_df['statistic'].append(paired_test(curr_df['RNA'][curr_df['period'] == 'Infancy'], per_df['RNA'].values)[0])

    if mode == 'coarse': scalar = 5
    elif mode== 'granular': scalar = (5*len(class_l))
    comp_df['padj_sig'] = np.asarray(comp_df['p value']) < 0.05/scalar
    comp_df = pd.DataFrame(comp_df)
    return(comp_df)


#=================================
def plot_null(null_df, sig_df, xsc, ysc):
#=================================

    """
    This function plots the null distribution of p values for each comparison, and 
    returns a new dataframe labelling all FDR sig comparisons as background significant or not.

    Inputs:
        null_df = dataframe containing all null distribution p values
        sig_df = dataframe containing all significant comparisons
        xsc = x scale of plot
        ysc = y scale of plot

    Outputs:
        final_df = dataframe containing all significant comparisons and whether they are background significant or not
    """

    import matplotlib.pyplot as plt
    import pandas as pd
    import math
    pd.options.mode.chained_assignment = None

    null_df['comb'] = null_df['celltype'] + '_' + null_df['Comparison']
    sig_df['comb'] = sig_df['celltype'] + '_' + sig_df['Comparison']
    cont = sig_df['comb'].unique()

    #Visualise null distribution
    plt.figure(figsize=(xsc, ysc))
    plt.subplots_adjust(hspace=0.5)
    final_df = pd.DataFrame()
    for x,c in enumerate(cont):
        ax = plt.subplot(int(math.ceil(len(cont)/3)), 3, x + 1)
        curr_data = null_df[null_df['comb']==c]['p value'].values
        #drop nan
        curr_data = curr_data[~np.isnan(curr_data)]
        sub_df = sig_df[sig_df['comb'] == c]
        #reset indeces
        sub_df.reset_index(inplace=True)

        #Loop through each comparison, Determine if significant, Group plot
        thresh = np.percentile(curr_data, 5)

        bins = np.geomspace(np.min(curr_data), np.max(curr_data), num=30)
        import seaborn as sns
        plt.title(c)
        sns.set_theme(style="darkgrid")
        plt.hist(curr_data, bins = bins)
        plt.axvline(x=thresh, color='k', linestyle='--')
        final_sig = np.array([])
        for i in range(len(sub_df)):
            if sub_df.loc[i]['p value'] <= thresh: 
                sig_str = 'sig'
                color = 'red'
                linewidth = 5
            else: 
                sig_str = 'not_sig'
                color = np.random.rand(3,)
            final_sig = np.append(final_sig, sig_str)
            plt.axvline(x=sub_df.loc[i]['p value'] , c=color, label = str(sub_df.loc[i]['Class']) + '_' + sig_str)
            
        #plt.legend in top left
        plt.legend(bbox_to_anchor=(0, 1), loc=2, borderaxespad=0.)
        plt.xscale('log')
        sub_df['baseline_sig'] = final_sig
        final_df = pd.concat([final_df, sub_df])
    plt.show()

    return(final_df)


#===========================================================
def bin_bed(df, binsize=1e3, upstream=5e4, downstream=5e4):
#===========================================================
    """
    This function takes as input a bed file of gene loci, and calculates a 
    binned bed file of positions up and downstream of the locus.
    
    Inputs:
        df (dataframe): bed file, with start, end, chr, strand, TEtype, TEfamily columns
        binsize (int): size of each bin in bed file
        upstream (int): number of bps upstream of locus to start bins
        downstream (int): number of bps downstream of locus to end bins
    
    Outputs:
        cat_df (dataframe): bed file with binned positions
    """
    
    
    import pandas as pd
    

    cat_df=[]
    for i in df.index:
      if df.loc[i,'strand']=='+':
        bins = df.loc[i,'start'] + np.arange(-upstream,downstream,binsize)
      else:
        bins = df.loc[i,'end'] + np.arange(upstream,-downstream,-binsize)

      bins_df=pd.DataFrame(index=np.arange(-upstream,downstream,binsize))
      bins_df['chr']=df.loc[i,'chr']
      bins_df['start']=bins
      bins_df['end']=bins+binsize
      bins_df['TE_start']=df.loc[i,'start']
      bins_df['TE_end']=df.loc[i,'end']
      bins_df['strand']=df.loc[i,'strand']
      bins_df['TE_type'] = df.loc[i,'TEtype']
      bins_df['TE_family'] = df.loc[i,'TEfamily']
      bins_df['TE_id'] = bins_df['chr']+'_'+bins_df['TE_family'].astype(str)+ '_' + bins_df['TE_start'].astype(str)+'_bin'+bins_df.index.astype(str)

      cat_df.append(bins_df)

    cat_df=pd.concat(cat_df).reset_index(drop=True)

    return(cat_df)



