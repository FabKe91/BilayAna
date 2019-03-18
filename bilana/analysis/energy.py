'''
    This module stores all functions that are needed to calculate the interaction energy of lipids or its parts
'''
import os
from . import neighbors
from .. import log
from ..common import exec_gromacs
from ..systeminfo import SysInfo
from ..definitions import lipidmolecules

LOGGER = log.LOGGER
LOGGER = log.create_filehandler("bilana_energy.log", LOGGER)

GMXNAME = "gmx"

class Energy(SysInfo):
    '''
        This class stores all information that is needed to automate the calculate the lipid interaction energy
        The main function is
            run_calculation
        For more information see its docstring
    '''

    DENOMINATOR = 40
    LOGGER = LOGGER

    def __init__(self,
        part,
        inputfilename="inputfile",
        neighborfilename='neighbor_info',
        resindex_all='resindex_all',
        overwrite=True,
        verbosity="INFO"):
        super().__init__(inputfilename)
        log.set_verbosity(verbosity)
        knownparts = ['complete', 'head-tail', 'head-tailhalfs', 'carbons']
        if part not in knownparts:
            raise ValueError("Part keyword specified is not known.")
        self.neiblist = neighbors.get_neighbor_dict()
        self.resindex_all = resindex_all
        self.overwrite = overwrite
        self.groupblocks = ()
        self.part = part
        if part == 'complete':
            self.molparts = ["resid_"]
            self.part = ''
            self.denominator = self.DENOMINATOR
            self.molparts_short = [""]
            if neighborfilename != 'neighbor_info':
                self.all_energies = 'all_energies_{}.dat'.format(neighborfilename)
            else:
                self.all_energies = 'all_energies.dat'
        elif part == 'head-tail':
            self.molparts = ["resid_h_", "resid_t_"]
            self.denominator = int(self.DENOMINATOR/2)
            self.molparts_short = ["h_", "t_"]
            self.all_energies='all_energies_headtail.dat'
        elif part == 'head-tailhalfs':
            self.molparts = ["resid_h_", "resid_t12_", "resid_t22_"]
            self.denominator = int(self.DENOMINATOR/4)
            self.molparts_short = ["h_","t12_","t22_"]
            self.all_energies = 'all_energies_headtailhalfs.dat'
        elif part == 'carbons':
            self.molparts = ['resid_C{}_'.format(i) for i in range(7)]
            self.denominator = int(self.DENOMINATOR/10)
            self.molparts_short = ['C{}_'.format(i) for i in range(7)]
            self.all_energies = "all_energies_carbons.dat"
        print('\n Calculating for energygroups:', self.molparts)

    def run_calculation(self, resids):
        ''' Runs an energy calculation with settings from Energy() instance.
            For each residue the energy to all neighbors seen during MD is calculated
            and written to .edr files.
            Procedure is as follows:
            1. The neighbors are divided into fragments ("groupfragments")
            2. For each fragment:
                an mdp file is created (create_MDP)
                a tpr file is generated (create_TPR)
            3. The actual mdrun -rerun is performed (do_Energyrun)
            4. .xvg tables are generate from .edr files

        '''
        print('''\n____Rerunning MD for energyfiles,
         creating xvgtables with relevant energies.____\n
         Caution mdp-file must not have energy_grps indicated!\n''')
        for res in resids:
            LOGGER.info('Working on lipid %s ...', res)
            all_neibs_of_res = list(set([neibs for t in self.neiblist[res].keys() for neibs in self.neiblist[res][t]]))
            nneibs = len(all_neibs_of_res)
            if nneibs % self.denominator == 0:
                number_of_groupfragments = (nneibs//self.denominator)
            else:
                number_of_groupfragments = (nneibs//self.denominator)+1
            LOGGER.info("Needing %s energy run(s)", number_of_groupfragments)
            for groupfragment in range(number_of_groupfragments):
                LOGGER.info("On fragment %s", groupfragment)

                g_energy_output = ''.join([\
                    self.energypath, '/xvgtables/energies_residue',\
                    str(res), '_', str(groupfragment), self.part, '.xvg',\
                    ])
                groupblockstart = groupfragment*self.denominator
                groupblockend = (groupfragment+1)*self.denominator
                self.groupblocks = (groupblockstart, groupblockend)

                # File in-/outputs
                groupfragment=str(groupfragment)
                mdpout = ''.join([self.energypath, 'mdpfiles/energy_mdp_recalc_resid', str(res), '_', groupfragment, self.part, '.mdp'])
                tprout = ''.join([self.energypath, 'tprfiles/mdrerun_resid', str(res), '_', groupfragment, self.part, '.tpr'])
                energyf_output = ''.join([self.energypath, 'edrfiles/energyfile_resid', str(res), '_'+groupfragment, self.part, '.edr'])
                xvg_out = ''.join([self.energypath, 'xvgtables/energies_residue', str(res), '_', groupfragment, self.part, '.xvg'])
                energygroups = self.gather_energygroups(res, all_neibs_of_res)
                relev_energies = self.get_relev_energies(res, all_neibs_of_res)

                # Run functions
                self.create_MDP(mdpout, energygroups)
                self.create_TPR(mdpout, tprout)
                if os.path.isfile(energyf_output) and not self.overwrite:
                    LOGGER.info("Edrfile for lipid %s part %s already exists. Will skip this calculation.", res, groupfragment)
                else:
                    self.do_Energyrun(res, groupfragment, tprout, energyf_output)
                if os.path.isfile(g_energy_output) and not self.overwrite:
                    LOGGER.info("Xvgtable for lipid %s part %s already exists. Will skip this calculation.", res, groupfragment)
                else:
                    self.write_XVG(energyf_output, tprout, relev_energies, xvg_out)
        return 1

    def selfinteractions_edr_to_xvg(self):
        ''' Extracts all self interaction energy values from .edr files using gmx energy '''
        for res in self.MOLRANGE:
            relev_energies = self.get_relev_self_interaction(res)
            tprout = ''.join([self.energypath, 'tprfiles/mdrerun_resid', str(res), '_', '0', self.part, '.tpr'])
            energyf_output = ''.join([self.energypath, 'edrfiles/energyfile_resid', str(res), '_'+'0', self.part, '.edr'])
            xvg_out = ''.join([self.energypath, 'xvgtables/energies_residue', str(res), '_selfinteraction', self.part, '.xvg'])
            self.write_XVG(energyf_output, tprout, relev_energies, xvg_out)
    def selfinteractions_xvg_to_dat(self):
        ''' Extracts all self interaction energy entries from xvg files
            and writes them to "selfinteractions.dat"
        '''
        with open("selfinteractions.dat", "w") as energyoutput:
            print(\
                  '{: <10}{: <10}'
                  '{: <20}{: <20}{: <20}{: <20}{: <20}{: <20}{: <20}'\
                  .format("Time", "Lipid",
                          "Etot", "VdWSR", "CoulSR", "VdW14", "Coul14", "VdWtot", "Coultot", ),
                  file=energyoutput)
            for resid in self.MOLRANGE:
                xvg_out = ''.join([self.energypath, 'xvgtables/energies_residue', str(resid), '_selfinteraction', self.part, '.xvg'])
                with open(xvg_out,"r") as xvgfile:
                    res_to_row = {}
                    for energyline in xvgfile: #folderlayout is: time Coul_resHost_resNeib LJ_resHost_resNeib ...
                        energyline_cols = energyline.split()
                        if '@ s' in energyline:                     #creating a dict to know which column(energies) belong to which residue
                            print(energyline_cols)
                            row = int(energyline_cols[1][1:])+1                 #time is at row 0 !
                            host = energyline_cols[3].split("resid_")[1][:-1]
                            energytype = energyline_cols[3].split(":")[0][1:]
                            #print("Host: {} Type: {} Row: {}".format(host, energytype, row))
                            res_to_row.update({(energytype, host):row})
                        elif '@' not in energyline and '#' not in energyline:     #pick correct energies from energyfile and print
                            time = float(energyline_cols[0])
                            #print("TIME", time)
                            if time % self.dt != 0:
                                continue
                            try:
                                vdw_sr = energyline_cols[res_to_row[('LJ-SR', str(host))]]
                                vdw_14 = energyline_cols[res_to_row[('LJ-14', str(host))]]
                                coul_sr = energyline_cols[res_to_row[('Coul-SR', str(host))]]
                                coul_14 = energyline_cols[res_to_row[('Coul-14', str(host))]]
                                vdw_tot = float(vdw_14) + float(vdw_sr)
                                coul_tot = float(coul_14) + float(coul_sr)
                            except KeyError:
                                continue
                            Etot = float(vdw_sr)+float(coul_sr)+float(vdw_14)+float(coul_14)
                            print(
                                  '{: <10}{: <10}{: <20.5f}'
                                  '{: <20}{: <20}{: <20}{: <20}{: <20.5f}{: <20.5f}'
                                  .format(time, resid,  Etot,
                                          vdw_sr, coul_sr, vdw_14, coul_14, vdw_tot, coul_tot,),
                                  file=energyoutput)

    def gather_energygroups(self, res, all_neibs_of_res):
        ''' Set which part of molecule should be considered '''
        energygroup_indeces = [res] + all_neibs_of_res[ self.groupblocks[0]:self.groupblocks[1] ]
        energygroup_list = []
        for index in energygroup_indeces:
            if self.resid_to_lipid[index] in lipidmolecules.STEROLS+lipidmolecules.PROTEINS:
                energygroup_list.append(''.join(["resid_",str(index)]))
            else:
                for part in self.molparts:
                    energygroup_list.append(''.join([part,str(index)]))
        energygroup_string = ' '.join(energygroup_list)
        return energygroup_string

    def get_relev_energies(self, res, all_neibs_of_res):
        '''
            Returns string that describes all entries
            needed to be extracted from energy file using gmx energy
            This version is for lipid-lipid interaction
            for self interaction search function "get_relev_self_interaction"
        '''
        Etypes=["Coul-SR:", "LJ-SR:"]
        energyselection=[]
        for interaction in Etypes:
            counterhost = 0 #for cholesterol as it has just 1 molpart
            for parthost in self.molparts:
                if self.resid_to_lipid[res] in (lipidmolecules.STEROLS + lipidmolecules.PROTEINS) and counterhost == 0:
                    parthost="resid_"
                    counterhost += 1
                elif self.resid_to_lipid[res] in (lipidmolecules.STEROLS + lipidmolecules.PROTEINS) and counterhost != 0:
                    continue
                for neib in all_neibs_of_res[self.groupblocks[0]:self.groupblocks[1]]:
                    counterneib = 0
                    for partneib in self.molparts:
                        if self.resid_to_lipid[neib] in (lipidmolecules.STEROLS + lipidmolecules.PROTEINS) and counterneib == 0:
                            partneib='resid_'
                            counterneib+=1
                        elif self.resid_to_lipid[neib] in (lipidmolecules.STEROLS + lipidmolecules.PROTEINS) and counterneib != 0:
                            continue
                        energyselection.append(''.join([interaction, parthost, str(res), "-", partneib,str(neib)]))
        all_relev_energies = '\n'.join(energyselection+['\n'])
        return all_relev_energies

    def get_relev_self_interaction(self, res):
        ''' Returns string that describes all entries
            needed to be extracted from energy file using gmx energy
            This version is for lipid self interaction
        '''
        Etypes=["Coul-SR:", "LJ-SR:", "Coul-14:", "LJ-14:"]
        energyselection=[]
        for interaction in Etypes:
            for parthost in self.molparts:
                energyselection.append(''.join([interaction,parthost,str(res),"-",parthost,str(res)]))
        all_relev_energies='\n'.join(energyselection+['\n'])
        return all_relev_energies

    def create_MDP(self, mdpout: str, energygroups: str):
        ''' Create mdpfile '''
        os.makedirs(self.energypath+'/mdpfiles', exist_ok=True)
        with open(mdpout,"w") as mdpfile_rerun:
            raw_mdp =[x.strip() for x in '''
            integrator              = md
            dt                      = 0.002
            nsteps                  =
            nstlog                  = 100000
            nstxout                 = 0
            nstvout                 = 0
            nstfout                 = 0
            nstcalcenergy           = 1000
            nstenergy               = 100
            cutoff-scheme           = Verlet
            nstlist                 = 20
            rlist                   = 1.2
            coulombtype             = pme
            rcoulomb                = 1.2
            vdwtype                 = Cut-off
            vdw-modifier            = Force-switch
            rvdw_switch             = 1.0
            rvdw                    = 1.2
            tcoupl                  = Nose-Hoover
            tau_t                   = 1.0
            tc-grps                 = System
            pcoupl                  = Parrinello-Rahman
            pcoupltype              = semiisotropic
            tau_p                   = 5.0
            compressibility         = 4.5e-5  4.5e-5
            ref_p                   = 1.0     1.0
            constraints             = h-bonds
            constraint_algorithm    = LINCS
            continuation            = yes
            nstcomm                 = 100
            comm_mode               = linear
            refcoord_scaling        = com
            '''.split('\n')]
            raw_mdp.append('ref_t = '+str(self.temperature))
            #mdp_raw_content = mdpfile_raw.readlines()
            #if not mdp_raw_content:
            #    raise EOFError(".mdp-file is empty")
            energygrpline = ''.join(['energygrps\t\t\t=', energygroups, '\n'])
            raw_mdp.append(energygrpline)
            mdpfile_rerun.write('\n'.join(raw_mdp)+'\n')

    def create_TPR(self, mdpoutfile: str, tprout: str):
        ''' Create TPRFILE with GROMPP '''
        os.makedirs(self.energypath+'tprfiles', exist_ok=True)
        grompp_arglist = [GMXNAME, 'grompp', '-f', mdpoutfile, '-p',\
                        self.toppath, '-c', self.gropath, '-o', tprout,\
                        '-n', self.resindex_all, '-po', mdpoutfile\
                        ]
        out, err = exec_gromacs(grompp_arglist)
        with open("gmx_grompp.log","a") as logfile:
            logfile.write(err)
            logfile.write(out)

    def do_Energyrun(self, res, groupfragment, tprrerun_in, energyf_out):
        ''' Create .edr ENERGYFILE with mdrun -rerun '''
        LOGGER.info('...Rerunning trajectory for energy calculation...')
        os.makedirs(self.energypath+'edrfiles', exist_ok=True)
        os.makedirs(self.energypath+'logfiles', exist_ok=True)
        logoutput_file = self.energypath+'logfiles/'+'mdrerun_resid'+str(res)+self.part+'frag'+groupfragment+'.log'
        trajout = 'EMPTY.trr' # As specified in mdpfile, !NO! .trr-file should be written
        mdrun_arglist = [GMXNAME, 'mdrun', '-s', tprrerun_in,'-rerun', self.trjpath,
                        '-e', energyf_out, '-o', trajout,'-g', logoutput_file,
                        ]
        out, err = exec_gromacs(mdrun_arglist)
        with open("gmx_mdrun.log","a") as logfile:
            logfile.write(err)
            logfile.write(out)

    def write_XVG(self, energyf_in, tprrerun_in, all_relev_energies, xvg_out):
        ''' Create XVG-TABLE with all relevant energies '''
        os.makedirs(self.energypath+'xvgtables', exist_ok=True)
        g_energy_arglist=[GMXNAME,'energy','-f',energyf_in,\
                          '-s', tprrerun_in,'-o', xvg_out,\
                          ]
        inp_str=all_relev_energies.encode()
        out, err = exec_gromacs(g_energy_arglist, inp_str)
        with open("gmx_energy.log","a") as logfile:
            logfile.write(err)
            logfile.write(out)

    def write_energyfile(self):
        ''' Creates files: "all_energies_<interaction>.dat
            NOTE: This function is too long. It should be separated into smaller parts.
        '''
        LOGGER.info('____ Create energy file ____')
        with open(self.all_energies, "w") as energyoutput:
            print(
                  '{: <10}{: <10}{: <10}{: <20}'
                  '{: <20}{: <20}{: <20}'\
                  .format("Time", "Host", "Neighbor", "Molparts",\
                                           "VdW", "Coul", "Etot"),\
                  file=energyoutput)
            for resid in self.MOLRANGE:
                LOGGER.info("Working on residue %s", resid)
                residtype = self.resid_to_lipid[resid]
                all_neibs_of_res = list(set([neibs for t in self.neiblist[resid].keys() for neibs in self.neiblist[resid][t]]))
                n_neibs = len(all_neibs_of_res)
                LOGGER.debug("All neibs of res %s are %s", resid, all_neibs_of_res)
                if n_neibs % self.denominator == 0:
                    number_of_groupfragments = (n_neibs//self.denominator)
                else:
                    number_of_groupfragments = (n_neibs//self.denominator)+1
                LOGGER.info("Nneibs: %s Nfrags: %s", n_neibs, number_of_groupfragments)
                processed_neibs = []
                for part in range(number_of_groupfragments):
                    LOGGER.debug("At part %s", part)
                    xvgfilename = self.energypath+'/xvgtables/energies_residue'+str(resid)+'_'+str(part)+self.part+'.xvg'
                    with open(xvgfilename,"r") as xvgfile:
                        res_to_row = {}
                        for energyline in xvgfile: #folderlayout is: time Coul_resHost_resNeib LJ_resHost_resNeib ...
                            energyline_cols = energyline.split()
                            if '@ s' in energyline:                     #creating a dict to know which column(energies) belong to which residue

                                row = int(energyline_cols[1][1:])+1                 #time is at row 0 !
                                #neib = REGEX_RESID.match(energyline_cols[3].split("resid_")[2][:-1]).groups()[0]
                                #host = REGEX_RESID.match(energyline_cols[3].split("resid_")[1][:-1]).groups()[0]
                                neib = energyline_cols[3].split("resid_")[2][:-1]
                                host = energyline_cols[3].split("resid_")[1][:-1]
                                energytype = energyline_cols[3].split("-")[0][1:]
                                LOGGER.debug("Hostid: %s, Neibid: %s", host, neib)
                                if energytype == 'LJ':
                                    processed_neibs.append(neib)
                                    #processed_neibs.append(int(neib))
                                    LOGGER.debug("Adding neib %s to processed", neib)
                                res_to_row.update({(energytype, host, neib):row})
                                LOGGER.debug("Adding to dict: Etype %s, host %s, neib %s", energytype, host, neib)
                            elif '@' not in energyline and '#' not in energyline:     #pick correct energies from energyfile and print
                                time = float(energyline_cols[0])
                                if time % self.dt != 0:
                                    continue
                                for neib in all_neibs_of_res:
                                    # This if statement is due to a broken simulation... In future it should be removed
                                    if self.system == 'dppc_dupc_chol25' and ((int(host) == 372 and neib == 242) or (int(host) == 242 and neib == 372)):
                                        continue
                                    neibtype = self.resid_to_lipid[neib]
                                    counterhost = 0
                                    for parthost in self.molparts:
                                        parthost = parthost[6:]
                                        if residtype == 'CHL1' and counterhost == 0:
                                            parthost = ''
                                            counterhost += 1
                                        elif residtype == 'CHL1' and counterhost != 0:
                                            continue
                                        counterneib = 0
                                        for partneib in self.molparts:
                                            partneib = partneib[6:]
                                            if neibtype == 'CHL1' and counterneib == 0:
                                                partneib = ''
                                                counterneib += 1
                                            elif neibtype == 'CHL1' and counterneib != 0:
                                                continue
                                            if parthost[:-1] == '':
                                                interhost = 'w'
                                            else:
                                                interhost = parthost[:-1]
                                            if partneib[:-1] == '':
                                                interneib = 'w'
                                            else:
                                                interneib = partneib[:-1]
                                            inter = ''.join([interhost, '_', interneib])
                                            #print(('LJ', parthost+str(resid), partneib+str(neib)))
                                            try:
                                                vdw = energyline_cols[res_to_row[('LJ', parthost+str(resid), partneib+str(neib))]]
                                                coul = energyline_cols[res_to_row[('Coul', parthost+str(resid), partneib+str(neib))]]
                                            except KeyError:
                                                #logger.debug("Couldnt find: %s, %s, ", parthost+str(resid), partneib+str(neib))
                                                continue
                                            Etot = float(vdw)+float(coul)
                                            #logger.debug("The output: host %s, neib %s, inter %s,", host, neib, inter)
                                            print(\
                                                  '{: <10}{: <10}{: <10}{: <20}'
                                                  '{: <20}{: <20}{: <20.5f}'
                                                  .format(time, resid, neib, inter,\
                                                                            vdw, coul, Etot),\
                                                  file=energyoutput)
                if LOGGER.level == 'DEBUG':
                    import collections
                    duplicates = [(item, count) for item, count in collections.Counter(processed_neibs).items() if count > 1]
                    LOGGER.debug(duplicates)
                if len(self.molparts) >1:
                    all_neibs_of_res = [part.replace("resid_", "")+str(entry) for entry in all_neibs_of_res for part in self.molparts] # Duplicating entries for each molpart
                    all_neibs_of_res = [entry for entry in all_neibs_of_res for _ in range(len(self.molparts))] # Duplicating entries for each molpart
                LOGGER.debug("All_neibs corrected %s", all_neibs_of_res)
                LOGGER.debug("Processed neibs: %s", processed_neibs)
                for pneib in processed_neibs:
                    LOGGER.debug("Pneib is: %s removing from %s", pneib, all_neibs_of_res)
                    all_neibs_of_res.remove(pneib)
                if all_neibs_of_res:
                    LOGGER.warning("Missing neighbour-ids: %s", all_neibs_of_res)
                    raise ValueError('Not all neighbours found in xvgfile')

    def check_exist_xvgs(self):
        ''' Checks if all .xvg-files containing lipid interaction exist '''
        all_okay = True
        with open("missing_xvgfiles.info", "w") as inffile:
            print("#Files missing", file=inffile)
            for resid in self.MOLRANGE:
                all_neibs_of_res = list(set([neibs for t in self.neiblist[resid].keys() for neibs in self.neiblist[resid][t]]))
                n_neibs = len(all_neibs_of_res)
                if n_neibs % self.denominator == 0:
                    number_of_groupfragments = (n_neibs//self.denominator)
                else:
                    number_of_groupfragments = (n_neibs//self.denominator)+1
                for part in range(number_of_groupfragments):
                    xvgfilename = self.energypath+'/xvgtables/energies_residue'+str(resid)+'_'+str(part)+self.part+'.xvg'
                    if not os.path.isfile(xvgfilename):
                        print(xvgfilename, file=inffile)
                        all_okay = False
        if not all_okay:
            LOGGER.warning('THERE ARE FILES MISSING')
        return all_okay