#
#  RoachCal routines to analyze standard set of observations done after
#  rebooting the ROACHes.
# 
#  The roachcal.scd schedule captures three sets of 1-s capture files,
#  named 
#     PRT<yyyymmddhhmmss>adc.dat   Blank sky observation with standard
#                                    observing sequence, solar.fsq,
#                                    ND-OFF, DCM attn set to 16 dB.
#                                    This is for generating the standard
#                                    DCM attenuation levels for each
#                                    antenna and IF crange.
#     PRT<yyyymmddhhmmss>ndon.dat  Blank sky observation with fixed
#                                    frequency (band23.fsq) and ND-ON.
#                                    This is for measuring relative X
#                                    vs. Y delay using autocorrelations.
#     PRT<yyyymmddhhmmss>ciel.dat  Observation on CIEL-2 Geosat, with
#                                    fixed frequency (band23.fsq).  This
#                                    is for measuring delays on each
#                                    antenna relative to Ant 1.
#  History
#   2017-01-08  DG
#     Changes to DCM_cal to make it more general, and to avoid messing up
#     current attenuation table for antennas that are missing.  The default
#     observing sequence is now the new gainseq.fsq, and ant15 is set as
#     missing.
#

import pcapture2 as p
import urllib2
import numpy as np

def DCM_cal(filename=None,fseqfile='gainseq.fsq',dcmattn=None,missing='ant15',update=False):

    if filename is None:
        return 'Must specify ADC packet capture filename, e.g. "/dppdata1/PRT/PRT<yyyymmddhhmmss>adc.dat"'

    userpass = 'admin:observer@'
    fseq_handle = urllib2.urlopen('ftp://'+userpass+'acc.solar.pvt/parm/'+fseqfile,timeout=0.5)
    lines = fseq_handle.readlines()
    fseq_handle.close()
    for line in lines:
        if line.find('LIST:SEQUENCE') != -1:
            line = line[14:]
            bandlist = np.array(map(int,line.split(',')))
    if len(np.unique(bandlist)) != 34:
        print 'Frequency sequence must contain all bands [1-34]'
        return None
    # Read packet capture file
    adc = p.rd_jspec(filename)
    pwr = rollaxis(adc['phdr'],2)[:,:,:2]
    # Put measured power into uniform array arranged by band
    new_pwr = np.zeros((34,16,2))
    for i in range(34):
        idx, = np.where(bandlist-1 == i)
        if len(idx) > 0:
            new_pwr[i] = np.median(pwr[idx],0)
    new_pwr.shape = (34,32)
    
    if dcmattn:
        # A DCM attenuation value was given, which presumes a constant value
        # so use it as the "original table."
        orig_table = np.zeros((34,30)) + dcmattn
        orig_table[:,26:] = 0
    else:
        # No DCM attenuation value was given, so read the current DCM master
        # table from the database.
        import cal_header
        import stateframe
        xml, buf = cal_header.read_cal(2)
        orig_table = stateframe.extract(buf,xml['Attenuation'])
        
    attn = np.log10(new_pwr[:,:-2]/1600.)*10.
    # Zero any changes for missing antennas
    if missing:
        idx = p.ant_str2list(missing)
        bad = np.sort(np.concatenate((idx*2,idx*2+1)))
        attn[:,bad] = 0
    new_table = (np.clip(orig_table + attn,0,30)/2).astype(int)*2
    DCMlines = []
    DCMlines.append('#      Ant1  Ant2  Ant3  Ant4  Ant5  Ant6  Ant7  Ant8  Ant9 Ant10 Ant11 Ant12 Ant13 Ant14 Ant15')
    DCMlines.append('#      X  Y  X  Y  X  Y  X  Y  X  Y  X  Y  X  Y  X  Y  X  Y  X  Y  X  Y  X  Y  X  Y  X  Y  X  Y')
    DCMlines.append('#     ----- ----- ----- ----- ----- ----- ----- ----- ----- ----- ----- ----- ----- ----- -----')
    for band in range(1,35):
        DCMlines.append('{:2} :  {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2} {:2}'.format(band,*new_table[band-1]))
    return DCMlines

def getphasecor(data, ant_str='ant1-14', polist=[0,1], crange=[0,4095], pplot=False):
    ''' Routine adapted from Maria Loukitcheva's code, to find phase slopes in
        correlated data on a geosynchronous satellite.
    '''
    def movingaverage(interval, window_size):
        # Range of ones, scaled for unit area
        window = np.ones(int(window_size)) / np.float(window_size)
        return np.convolve(interval, window, 'same')

    antlist = p.ant_str2list(ant_str)
    print antlist+1
    ndon = False
    if len(data[:,0,0,0]) == 16:
        ndon = True
    if ndon:
        chlist = antlist
    else:
        chlist = antlist[1:]-1
    bl2ord = p.bl_list()
    if not ndon: 
        data = data[bl2ord[0,1:]]   # Consider only baselines with antenna 1
    print data.shape
    pcor = np.linspace(0, np.pi, 4096) 
    istep = np.arange(-50,50)   # Range of steps to search
    chan = np.arange(4096)
    phasecor = np.zeros((14, len(polist)))
    
    start=crange[0]
    end=crange[1]
    #antennalist=[2]

    if pplot:
        import matplotlib.pylab as plt
        f, ax = plt.subplots(len(antlist),len(polist))

    for i,iant in enumerate(chlist):
        for j,jpol in enumerate(polist):
            phaseall = np.zeros(len(istep))
            for k in range(len(istep)):
                #if movaver: 
                #    aver = movingaverage(data[bl2ord[0, antennalist[i]], j, :, 0],201)
                #    aver = cos(angle(aver) + istep[k] * pcor)
                #else:   
                aver = np.cos(2*(np.angle(data[iant, jpol, :, 0]) + istep[k] * pcor))
                phaseall[k] = np.polyfit(chan[start:end], aver[start:end], 0, full=True)[1]
            #print phaseall
            #print argmin(drange)
            #print corind[argmin(drange)]
            ioff = iant+1
            if ndon: ioff = iant
            phasecor[ioff, j] = - istep[np.argmin(phaseall)]  # Correct delay is negative of the phase correction
            phas0 = np.angle(data[iant, jpol, :, 0])
            phas = phas0 + istep[np.argmin(phaseall)] * pcor
            if pplot:
                if ndon:
                    iax = i
                else:
                    iax = i+1
                if len(polist) > 1: 
                    ax[iax,j].plot(phas0 % (2*np.pi), '.')
                    ax[iax,j].plot(phas % (2*np.pi), '.')
                    ax[iax,j].plot(chan[start:end],phas[start:end] % (2*np.pi),color='white')
                    ax[iax,j].set_ylim(-1,7)
                else:
                    ax[iax].plot(phas0 % (2*np.pi), '.')
                    ax[iax].plot(phas % (2*np.pi), '.')
                    ax[iax].plot(chan[start:end],phas[start:end] % (2*np.pi),color='white')
                    ax[iax].set_ylim(-1,7)
    if len(polist) == 1:
        # Reduce two-dimensional array with second dimension = 1 to a single dimension
        return phasecor[:,0]
    return phasecor

