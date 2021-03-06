#!/usr/bin/env python3
########################################################################
# Stack processing using GAMMA for SBAS or phase-stacking processing   #
# [ generating ifg by number of connections ]                          #
# Copyright (c) 2020, Lei Yuan                                         #
########################################################################

import os
import re
import sys
import glob
import argparse

dinsar_script = """m_slc=$slc_dir/$m_date/$m_date.slc
s_slc=$slc_dir/$s_date/$s_date.slc
m_par=$m_slc.par
s_par=$s_slc.par
MS_off=$m_date-$s_date.off

##################################################################################################################
### create the ISP processing/offset parameter file from MSP processing parameter and sensor files
##################################################################################################################
# par_MSP ../$m_date/palsar.par ../$m_date/p$m_par $m_par
# par_MSP ../$s_date/palsar.par ../$s_date/p$s_par $s_par
##################################################################################################################
### Supports interactive creation of offset/processing parameter file for generation of interferograms
### create_offset reads the SLC parameter files and queries the user for parameters(write into the .off file) required to calculate the offsets 
### using either the cross correlation of intensity or fringe visibility algorithms
### a. scence title: interferogram parameters
### b. range,azimuth offsets of SLC-2 relative to SLC-1(SLC samples):0 0
### c. enter number of offset measurements in range, azimuth: 32 32
### e. search window sizes(range, azimuth, nominal: 64 64)
### f. low correlation SNR threshold for intensity cross correlation 7.0
### g. offset in range to first interfergram sample 0
### h. width of SLCsection to processes (width of SLC-1)
##################################################################################################################
echo -ne "$m_date-$s_date\\n 0 0\\n 32 32\\n 64 64\\n 7.0\\n 0\\n\\n" > create_offset
create_offset $m_par $s_par $MS_off 1 1 1 < create_offset
rm -f create_offset

##################################################################################################################
### first guess of the offsets can be obtained based on orbital information
### The position of the initial registration offset estimation can be indicated. As default the SLC-1 image center is used.
##################################################################################################################
init_offset_orbit $m_par $s_par $MS_off

##################################################################################################################
### improve the first guess, determines the initial offsets based on the cross-correlation function of the image intensities
### In order to avoid ambiguity problems and achieve an accutare estimates init_offset first be run with multi-looking
### followed by a second run at single look resolution
##################################################################################################################
init_offset $m_slc $s_slc $m_par $s_par $MS_off 9 10
init_offset $m_slc $s_slc $m_par $s_par $MS_off 1 1

##################################################################################################################
### Generation of interferogram with multi-look factors rlks * alks
##################################################################################################################
SLC_intf $m_slc $s_slc $m_par $s_par $MS_off $m_date-$s_date.int $rlks $alks - - 1 1

##################################################################################################################
### Generation of multi-look SARintensity image of reference SLC
##################################################################################################################
multi_look $m_slc $m_par  $m_date-$s_date.pwr1 $m_date.pwr1.par $rlks $alks
multi_look $s_slc $s_par $m_date-$s_date.pwr2 $s_date.pwr2.par $rlks $alks
width=$(awk '$1 == "interferogram_width:" {print $2}' $MS_off)
line=$(awk '$1 == "interferogram_azimuth_lines:" {print $2}' $MS_off)
rasmph_pwr $m_date-$s_date.int $m_date-$s_date.pwr1 $width 1 1 0 1 1 1. 0.35 1 $m_date-$s_date.intandpwr.bmp
raspwr $m_date-$s_date.pwr1 $width 1 0 1 1 1. 0.35 1 $m_date-$s_date.pwr1.bmp
raspwr $m_date-$s_date.pwr2 $width 1 0 1 1 1. 0.35 1 $m_date-$s_date.pwr2.bmp
base_init $m_par $s_par $MS_off $m_date-$s_date.int $m_date-$s_date.base 0 1024 1024
base_perp $m_date-$s_date.base $m_par $MS_off > $m_date-$s_date.base.perp

##################################################################################################################
### Curved Earth phase trend removal("flattening")
### ph_slop_base Subtract/add interferogram flat-Earth phase trend as estimated from initial baseline
##################################################################################################################
ph_slope_base $m_date-$s_date.int $m_par $MS_off $m_date-$s_date.base $m_date-$s_date.flt 1 0
rasmph_pwr $m_date-$s_date.flt $m_date-$s_date.pwr1 $width 1 1 0 1 1 1. 0.35 1 $m_date-$s_date.fltandpwr.bmp
cc_wave $m_date-$s_date.int $m_par $s_par $m_date-$s_date.corr $width - - 3

##################################################################################################################
### filter flattened interferogram
##################################################################################################################
adf $m_date-$s_date.flt $m_date-$s_date.flt.sm1 $m_date-$s_date.sm.cc1 $width 0.3 128
adf $m_date-$s_date.flt.sm1 $m_date-$s_date.flt.sm2 $m_date-$s_date.sm.cc2 $width 0.3 64
adf $m_date-$s_date.flt.sm2 $m_date-$s_date.flt.sm $m_date-$s_date.sm.cc $width 0.3
rasmph_pwr $m_date-$s_date.flt.sm $m_date-$s_date.pwr1 $width 1 1 0 1 1 1. 0.35 1 $m_date-$s_date.fltsmpwr.bmp
gc_map $m_par $MS_off $dem_par $dem dem_seg.par dem_seg lookup 1 1 sim_sar - - - - - - 8 1
width_map=$(awk '$1 == "width:" {print $2}' dem_seg.par)
nlines_map=$(awk '$1 == "nlines:" {print $2}' dem_seg.par)
col_post=$(awk '$1 == "post_lat:" {print $2}' dem_seg.par)
row_post=$(awk '$1 == "post_lon:" {print $2}' dem_seg.par)
rasshd dem_seg $width_map $col_post $row_post 1 0 1 1 45. 135. 1 dem_seg.bmp

##################################################################################################################
### geocode the simulated SAR intensity image to radar coordinate
### when gc_map computes the lookup table it can also compute a simulated SAR image in the map coordinate system
### geocode:Forward transformation with a geocoding look-up table
### For each image point defined in coordinate system A, the lookup table contains the corresponding coordinates in system B
### The program geocode is used to resample the data in coordinate system A into the coordinates of system B
##################################################################################################################
geocode lookup sim_sar $width_map sim_sar_rdc $width $line 1 0
raspwr sim_sar_rdc $width 1 0 1 1 1. .35 1 sim_sar_rdc.bmp

##################################################################################################################
### create a parameter file including the differential interferogram parameters
### create_diff_par: reads two parameter files(.off,.slc.par,.mli.par,.dem_datear)and creates a DIFF parameter file used for 
### image registration,geocoding, and 2- and 3-pass differential interferometry
##################################################################################################################
echo -ne "$m_date-$s_date\\n 0 0\\n 64 64\\n 256 256\\n 7.0\\n" > create_diff_parin
create_diff_par $MS_off - $m_date-$s_date.diff.par 0 < create_diff_parin
rm -f create_diff_parin

##################################################################################################################
### compute offset of simulated SAR image to slc(mli) image
### init_offsetm: initial registration offset estimation for multilook intensity images
### offset_pwrm: estimates the range and azimuth registration offset fields using cross correlation optimization of the input intensity images
### offset_fitm: computes range and azimuth registration offset polynomials from offsets estimated by one of the program offset_pwrm or offset_pwr_tracking 
##################################################################################################################
init_offsetm $m_date-$s_date.pwr1 sim_sar_rdc $m_date-$s_date.diff.par 1 1 - - 0 0 7
offset_pwrm $m_date-$s_date.pwr1 sim_sar_rdc $m_date-$s_date.diff.par offs snr 256 256 offsets 2 100 100 7.0 2
offset_fitm offs snr $m_date-$s_date.diff.par coffs coffsets 8.0 6
offset_pwrm $m_date-$s_date.pwr1 sim_sar_rdc $m_date-$s_date.diff.par offs snr 64 64 offsets 2 300 300 9.0 2
offset_fitm offs snr $m_date-$s_date.diff.par coffs coffsets 10.0 6

##################################################################################################################
### gc_map_fine applies the fine registration function to the input lookup table to create the refined output lookup table 
### This is done by addition of the fine registration offsets to the lookup vectors
##################################################################################################################
gc_map_fine lookup $width_map $m_date-$s_date.diff.par lookup_fine 0
geocode lookup_fine dem_seg $width_map $m_date-$s_date.rdc_hgt $width $line 1 0
rashgt $m_date-$s_date.rdc_hgt $m_date-$s_date.pwr1 $width 1 1 0 1 1 20.0 1. .35 1 $m_date-$s_date.rdc_hgt_pwr.bmp

##################################################################################################################
### Form Differential Interferogram (flag is important)
##################################################################################################################
# simulation of unwrapped topographic phase
phase_sim $m_par $MS_off $m_date-$s_date.base $m_date-$s_date.rdc_hgt $m_date-$s_date.sim_unw 0 0 - -

##################################################################################################################
### Subtractiing the simulated unwrapped phase from the complex interferogram
##################################################################################################################
sub_phase $m_date-$s_date.int $m_date-$s_date.sim_unw $m_date-$s_date.diff.par $m_date-$s_date.diff.int 1 0
rasmph $m_date-$s_date.diff.int $width 1 0 1 1 1. 0.35 1 $m_date-$s_date.diff.int.bmp
rasmph_pwr $m_date-$s_date.diff.int $m_date-$s_date.pwr1 $width 1 1 0 1 1 1. 0.35 1 $m_date-$s_date.diff.int.pwr.bmp

##################################################################################################################
### Filter Differential Interferogram
##################################################################################################################
adf $m_date-$s_date.diff.int $m_date-$s_date.diff.int.sm1 $m_date-$s_date.diff.sm.cc1 $width 0.3 128
adf $m_date-$s_date.diff.int.sm1 $m_date-$s_date.diff.int.sm2 $m_date-$s_date.diff.sm.cc2 $width 0.3 64
adf $m_date-$s_date.diff.int.sm2 $m_date-$s_date.diff.int.sm $m_date-$s_date.diff.sm.cc $width 0.3
rasmph $m_date-$s_date.diff.int.sm $width 1 0 1 1 1. 0.35 1 $m_date-$s_date.diff.int.sm.bmp
rasmph_pwr $m_date-$s_date.diff.int.sm $m_date-$s_date.pwr1 $width 1 1 0 1 1 1. 0.35 1 $m_date-$s_date.diff.int.sm.pwr.bmp

##################################################################################################################
### Unwrap Differential Flattened Interferogram
##################################################################################################################
# rascc_mask $m_date-$s_date.sm.cc $m_date-$s_date.pwr1 $width 1 1 0 1 1 0.0 0. .1 .9 1. .35 1 $m_date-$s_date.sm.cc_mask.bmp
rascc_mask $m_date-$s_date.corr $m_date-$s_date.pwr1 $width 1 1 0 1 1 0.0 0. .1 .9 1. .35 1 $m_date-$s_date.sm.cc_mask.bmp
mcf $m_date-$s_date.diff.int.sm $m_date-$s_date.corr $m_date-$s_date.sm.cc_mask.bmp $m_date-$s_date.diff.int.sm.unw $width 1 0 0 - - 1 1 - - - 0
rasrmg $m_date-$s_date.diff.int.sm.unw $m_date-$s_date.pwr1 $width 1 1 0 1 1 .6 1. .35 .0 1 $m_date-$s_date.diff.int.sm.unw.pwr.bmp $m_date-$s_date.sm.cc 1 .2
rasrmg $m_date-$s_date.diff.int.sm.unw - $width 1 1 0 1 1 .5 1. .35 .0 1 $m_date-$s_date.diff.int.sm.unw.bmp $m_date-$s_date.sm.cc 1 .2

##################################################################################################################
### Subtractiing linear phase trends if needed 
##################################################################################################################
quad_fit $m_date-$s_date.diff.int.sm.unw $m_date-$s_date.diff.par 32 32 $m_date-$s_date.sm.cc_mask.bmp $m_date-$s_date.plot 3
quad_sub $m_date-$s_date.diff.int.sm.unw $m_date-$s_date.diff.par $m_date-$s_date.diff.int.sm.sub.unw 0 0
rasrmg $m_date-$s_date.diff.int.sm.sub.unw $m_date-$s_date.pwr1 $width 1 1 0 1 1 .6 1. .35 .0 1 $m_date-$s_date.diff.int.sm.sub.unw.pwr.bmp $m_date-$s_date.sm.cc 1 .2
rasrmg $m_date-$s_date.diff.int.sm.sub.unw -  $width 1 1 0 1 1 .5 1. .35 .0 1 $m_date-$s_date.diff.int.sm.sub.unw.bmp $m_date-$s_date.sm.cc 1 .2

##################################################################################################################
### geocode the radar coordinates to imulated SAR intensity image
##################################################################################################################
# geocode_back $m_date-$s_date.sm.cc $width lookup_fine $m_date-$s_date.utm.cc $width_map $nlines_map 1 0
# geocode_back $m_date-$s_date.diff.int.sm $width lookup_fine $m_date-$s_date.diff.utm.sm $width_map $nlines_map 1 1
# geocode_back $m_date-$s_date.diff.int.sm.unw $width lookup_fine $m_date-$s_date.diff.utm.unw $width_map $nlines_map 1 0
# geocode_back $m_date-$s_date.pwr1 $width lookup_fine $m_date-$s_date.utm.pwr $width_map $nlines_map 1 0
# rascc $m_date-$s_date.utm.cc - $width_map 1 1 0 1 1 .1 .9 1. .35 1 $m_date-$s_date.utm.cc.bmp
# rascc $m_date-$s_date.utm.cc $m_date-$s_date.utm.pwr $width_map 1 1 0 1 1 .1 .9 1. .35 1 $m_date-$s_date.utm.ccandpwr.bmp
# rasmph $m_date-$s_date.diff.utm.sm $width_map 1 0 1 1 1. 0.35 1 $m_date-$s_date.diff.utm.sm.bmp
# rasmph_pwr $m_date-$s_date.diff.utm.sm $m_date-$s_date.utm.pwr $width_map 1 1 0 1 1 1. 0.35 1 $m_date-$s_date.diff.utm.smandpwr.bmp
# rasrmg $m_date-$s_date.diff.int.sm.unw -  $width 1 1 0 1 1 .18 1. .35 .0 1 $m_date-$s_date.diff.int.unw.bmp $m_date-$s_date.sm.cc 1 .2
"""


def cmd_line_parser():
    parser = argparse.ArgumentParser(description='Stack processing using GAMMA for SBAS or phase-stacking processing.',\
                                     formatter_class=argparse.RawTextHelpFormatter,\
                                     epilog=EXAMPLE)

    parser.add_argument('slc_dir', help='directory path of slc')
    parser.add_argument('stacking_dir', help='directory path of stacking')
    parser.add_argument('dem_dir', help='directory path of dem and dem.par')
    parser.add_argument(
        'num_connections',
        help='number of interferograms between each date and subsequent dates',
        type=int)
    parser.add_argument('--rlks',
                        help='range looks (defaults: 20)',
                        default=20,
                        type=int)
    parser.add_argument('--alks',
                        help='azimuth looks (defaults: 5)',
                        default=5,
                        type=int)
    inps = parser.parse_args()

    return inps


EXAMPLE = """Example:
  ./diff_by_number_nocoreg.py /ly/slc /ly/stacking /ly/dem 4
  ./diff_by_number_nocoreg.py /ly/slc /ly/stacking /ly/dem 4 --rlks 8 --alks 2
"""


def gen_ifg_pairs(slc_date, num_connections):
    slc_date = sorted(slc_date)
    ifg_pairs = []
    length = len(slc_date)
    for i in range(length):
        if i < length - num_connections:
            for j in range(num_connections):
                ifg_pairs.append(f"{slc_date[i]}_{slc_date[i + j + 1]}")
        else:
            for k in range(length - i - 1):
                ifg_pairs.append(f"{slc_date[i]}_{slc_date[i + k + 1]}")
    return ifg_pairs


def main():
    inps = cmd_line_parser()
    # get inputs
    slc_dir = inps.slc_dir
    stacking_dir = inps.stacking_dir
    num_connections = inps.num_connections
    dem_dir = inps.dem_dir
    rlks = inps.rlks
    alks = inps.alks

    slc_dir = os.path.abspath(slc_dir)
    stacking_dir = os.path.abspath(stacking_dir)
    dem_dir = os.path.abspath(dem_dir)

    # check dem and dem.par
    if os.path.isdir(dem_dir):
        dem = glob.glob(dem_dir + '/*.dem')
        dem_par = glob.glob(dem_dir + '/*.dem.par')
        if dem and dem_par:
            dem = dem[0]
            dem_par = dem_par[0]
        else:
            print('dem or dem.par not exists.')
            sys.exit(1)
    else:
        print('{} not exists.'.format(dem_dir))
        sys.exit(1)

    if not os.path.isdir(stacking_dir):
        os.mkdir(stacking_dir)

    # get all date
    tmp_files = os.listdir(slc_dir)
    slc_date = [i for i in tmp_files if re.match(r'^\d{8}$', i)]

    # generate ifg_pair
    ifg_pairs = gen_ifg_pairs(slc_date, num_connections)

    for i in ifg_pairs:
        # make ifg_pair dir
        path = os.path.join(stacking_dir, i)
        if not os.path.isdir(path):
            os.mkdir(path)

        # write dinsar script
        m_date = i[0:8]
        s_date = i[9:17]

        str_m_date = f"m_date={m_date}\n"
        str_s_date = f"s_date={s_date}\n"
        str_slc_dir = f"slc_dir={slc_dir}\n"
        str_dem = f"dem={dem}\n"
        str_dem_par = f"dem_par={dem_par}\n"
        str_rlks = f"rlks={rlks}\n"
        str_alks = f"alks={alks}\n"

        out_script = '#!/bin/sh\n\n' + str_m_date + str_s_date + str_slc_dir + str_dem + str_dem_par + str_rlks + str_alks + dinsar_script
        out_script_path = os.path.join(path, i + '_DInSAR.sh')
        with open(out_script_path, 'w+') as f:
            f.write(out_script)
        # run dinsar script
        os.chdir(path)
        call_str = 'sh ' + i + '_DInSAR.sh'
        os.system(call_str)


if __name__ == "__main__":
    main()
