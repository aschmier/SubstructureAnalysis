#! /usr/bin/env python3

import argparse
import getpass
import logging
import os
import pwd
import shutil
import subprocess
import sys
import time

def submit(command: str, jobname: str, logfile: str, partition: str = "short", numnodes: int = 1, numtasks: int = 1, jobarray = None, dependency=0) -> int:
    submitcmd = "sbatch -N {NUMNODES} -n {NUMTASKS} --partition={PARTITION}".format(NUMNODES=numnodes, NUMTASKS=numtasks, PARTITION=partition)
    if jobarray:
        submitcmd += " --array={ARRAYMIN}-{ARRAYMAX}".format(ARRAYMIN=jobarray[0], ARRAYMAX=jobarray[1])
    if dependency > 0:
        submitcmd += " -d {DEP}".format(DEP=dependency)
    submitcmd += " -J {JOBNAME} -o {LOGFILE} {COMMAND}".format(JOBNAME=jobname, LOGFILE=logfile, COMMAND=command)
    logging.debug("Submitcmd: {}".format(submitcmd))
    submitResult = subprocess.run(submitcmd, shell=True, stdout=subprocess.PIPE)
    sout = submitResult.stdout.decode("utf-8")
    toks = sout.split(" ")
    jobid = int(toks[len(toks)-1])
    return jobid

class AliTrainDB:

    class UninitializedException(Exception):

        def __init__(self):
            super().__init__()
    
        def __str__(self):
            return "Train database not initialized"

    class TrainNotFoundException(Exception):

        def __init__(self, trainID: int):
            super().__init__()
            self.__trainID = trainID

        def __str__(self):
            return "No train found for ID {}".format(self.__trainID)

        def getTrainID(self) -> int:
            return self.__trainID

    def __init__(self, pwg: str, train: str):
        self.__pwg = pwg
        self.__train = train
        self.__trains = {}
        self.__initialized = False
        self.__build()

    def __build(self):
        trainsraw = subprocess.getstatusoutput("alien_ls /alice/cern.ch/user/a/alitrain/{}/{}".format(self.__pwg, self.__train))
        if trainsraw[0] != 0:
            logging.error("Failed building trains DB for train %s/%s", self.__pwg, self.__train)
        for trainstring in trainsraw[1].split("\n"):
            tmpstring = trainstring.replace("/", "").lstrip().rstrip()
            if "_child" in tmpstring:
                tmpstring = tmpstring[0:tmpstring.index("_child")]
            trainID = int(tmpstring.split("_")[0])
            if not trainID in self.__trains.keys():
                logging.debug("{}: Adding ID {}".format(trainID, tmpstring))
                self.__trains[trainID] = tmpstring
        self.__initialized = True

    def getTrainIdentifier(self, trainID: int) -> str:
        if not self.__initialized:
            raise AliTrainDB.UninitializedException()
        if not trainID in self.__trains.keys():
            raise AliTrainDB.TrainNotFoundException(trainID)
        return self.__trains[trainID] 


class LaunchHandler:

    def __init__(self, repo: str, outputbase: str , trainrun: int, legotrain: str):
        self.__repo = repo
        self.__outputbase = outputbase
        self.__legotrain = legotrain
        self.__trainrun = None
        self.__partitionDownload = "long"
        self.__tokens = {"cert": None, "key": None}

        pwg,trainname = self.__legotrain.split("/")
        trainDB = AliTrainDB(pwg, trainname)
        try:
            self.__trainrun = trainDB.getTrainIdentifier(trainrun)
        except AliTrainDB.UninitializedException as e:
            logging.error("%s", e)
        except AliTrainDB.TrainNotFoundException as e:
            logging.error("%s", e)

    def set_partition_for_download(self, partition: str):
        if not partition in ["long", "short", "vip", "loginOnly"]:
            return
        self.__partitionDownload = partition

    def set_token(self, cert: str, key: str):
        self.__tokens["cert"] = cert
        self.__tokens["key"] = key

    def submit(self, year: int, subsample: str = ""):
        if not self.__trainrun:
            logging.error("Failed initializing train run")
            return
        mcsamples = {2016: ["LHC19a1a_1", "LHC19a1a_2", "LHC19a1b_1", "LHC19a1b_2", "LHC19a1c_1", "LHC19a1c_2"], 2017: ["LHC18f5_1", "LHC18f5_2"], 2018: ["LHC19d3_1", "LHC19d3_1_extra", "LHC19d3_2", "LHC19d3_2_extra"]}
        if not year in mcsamples.keys():
            logging.error("No sample or year %d", year)
        if len(subsample):
            if not subsample in mcsamples[year]:
                logging.error("Requested subsample %s not found for year %d ...", subsample, year)
                return
        for sample in mcsamples[year]:
            select = False
            if len(subsample):
                if sample == subsample:
                    select = True
            if not select:
                continue
            jobid_download = self.submit_download_MC(sample)
            if not jobid_download:
                return
            logging.info("Submitting download job with ID: {}".format(jobid_download))
            self.submit_merge(sample, jobid_download)

    def submit_download_MC(self, sample: str) -> int:
        cert = self.__tokens["cert"]
        key = self.__tokens["key"]
        if not key or not cert:
            logging.error("Alien token not provided - cannot download ...")
            return None
        executable = os.path.join(self.__repo, "runDownloadAndMergeMCBatch.sh")
        jobname = "down_{SAMPLE}".format(SAMPLE=sample)
        outputdir = os.path.join(self.__outputbase, sample)
        if not os.path.exists(outputdir):
            os.makedirs(outputdir, 0o755)
        logfile = os.path.join(outputdir, "download.log")
        
        downloadcmd = "{EXE} {DOWNLOADREPO} {OUTPUTDIR} {DATASET} {LEGOTRAIN}/{TRAINID} {ALIEN_CERT} {ALIEN_KEY}".format(EXE=executable, DOWNLOADREPO=self.__repo, OUTPUTDIR=outputdir, DATASET=sample, LEGOTRAIN=self.__legotrain, TRAINID=self.__trainrun, ALIEN_CERT=cert, ALIEN_KEY=key)
        jobid = submit(command=downloadcmd, jobname=jobname, logfile=logfile, partition=self.__partitionDownload, numnodes=1, numtasks=4)
        return jobid

    def submit_merge(self, sample: str, wait_jobid: int) -> int:
        substructure_repo = "/software/markus/alice/SubstructureAnalysis"
        executable = os.path.join(substructure_repo, "merge", "submitMergeRun.py")
        workdir = os.path.join(self.__outputbase, sample)
        mergecommand = "{EXE} {WORKDIR} -w {DEP}".format(EXE=executable, WORKDIR=workdir, DEP=wait_jobid)
        subprocess.call(mergecommand, shell=True)

class AlienToken:

    def __init__(self, dn: str, issuer: str, begin: time.struct_time, end: time.struct_time):
        self.__dn = dn
        self.__issuer = issuer
        self.__begin = begin
        self.__end = end

    def set_begin(self, begin: time.struct_time):
        self.__begin = begin

    def set_end(self, end: time.struct_time):
        self.__end = end
    
    def set_dn(self, dn: str):
        self.__dn = dn

    def set_issuer(self, issuer: str):
        self.__issuer = issuer

    def get_begin(self) -> time.struct_time:
        return self.__begin

    def get_end(self) -> time.struct_time:
        return self.__end

    def get_dn(self) -> str:
        return self.__dn

    def get_issuer(self) -> str:
        return self.__issuer


def parse_time(token_timestring: str):
    return time.strptime(token_timestring, "%Y-%m-%d %H:%M:%S")

def get_token_info(tokencert: str, tokenkey: str):
    testcmd="export JALIEN_TOKEN_CERT={ALIEN_CERT}; export JALIEN_TOKEN_KEY={ALIEN_KEY}; alien-token-info".format(ALIEN_CERT=tokencert, ALIEN_KEY=tokenkey)
    testres = subprocess.getstatusoutput(testcmd)
    if testres[0] != 0:
        logging.error("Tokenfiles %s and %s invalid ...", tokencert, tokenkey)
        return None
    infos = testres[1].split("\n")
    dn = ""
    issuer = ""
    start = None
    end = None
    for en in infos:
        keyval = en.split(">>>")
        key = keyval[0].lstrip().rstrip()
        value = keyval[1].lstrip().rstrip()
        if key == "DN":
            dn = value
        elif key == "ISSUER":
            issuer = value
        elif key == "BEGIN":
            start = parse_time(value)
        elif key == "EXPIRE":
            end = parse_time(value)
    return AlienToken(dn, issuer, start, end)

def test_alien_token():
    result = {}
    me = getpass.getuser()
    userid = pwd.getpwnam(me).pw_uid
    cluster_tokenrepo = os.path.join("/software", me, "tokens")
    cluster_tokencert = os.path.join(cluster_tokenrepo, "tokencert_%d.pem" %userid)
    cluster_tokenkey = os.path.join(cluster_tokenrepo, "tokenkey_%d.pem" %userid)
    if not os.path.exists(cluster_tokencert) or not os.path.exists(cluster_tokenkey):
        logging.error("Either token certificate or key missing ...")
        return result
    tokeninfo = get_token_info(cluster_tokencert, cluster_tokenkey)
    now = time.localtime()
    timediff_seconds = time.mktime(tokeninfo.get_end()) - time.mktime(now)
    two_hours = 2 * 60 * 60
    if timediff_seconds > two_hours:
        # accept token if valid > 2 hours
        result = {"cert": cluster_tokencert, "key": cluster_tokenkey}
    return result

def recreate_token():
    me = getpass.getuser()
    userid = pwd.getpwnam(me).pw_uid
    cluster_tokenrepo = os.path.join("/software", me, "tokens")
    cluster_tokencert = os.path.join(cluster_tokenrepo, "tokencert_%d.pem" %userid)
    cluster_tokenkey = os.path.join(cluster_tokenrepo, "tokenkey_%d.pem" %userid)
    tmp_tokencert = os.path.join("/tmp", "tokencert_%d.pem" %userid)
    tmp_tokenkey = os.path.join("/tmp", "tokenkey_%d.pem" %userid)
    subprocess.call("alien-token-init", shell=True)
    shutil.copyfile(tmp_tokencert, cluster_tokencert)
    shutil.copyfile(tmp_tokenkey, cluster_tokenkey)
    return {"cert": cluster_tokencert, "key": cluster_tokenkey}

if __name__ == "__main__":
    currentbase = os.getcwd()
    repo = os.path.dirname(os.path.abspath(sys.argv[0]))
    parser = argparse.ArgumentParser("submitDownloadAndMergeMC.py", description="submitter for download and merge")
    parser.add_argument("-o", "--outputdir", metavar="VARIATION", type=str, default=currentbase, help="Output directory (default: current directory)")
    parser.add_argument("-y", "--year", metavar="YEAR", type=int,required=True, help="Year of the sample")
    parser.add_argument("-t", "--trainrun", metavar="TRAINRUN", type=int, required=True, help="Train run (only main number)")
    parser.add_argument("-l", "--legotrain", metavar="LEGOTRAIN", type=str, default="PWGJE/Jets_EMC_pp_MC", help="Name of the lego train (default: PWGJE/Jets_EMC_pp_MC)")
    parser.add_argument("-s", "--subsample", metavar="SUBSAMPLE", type=str, default="", help="Copy only subsample")
    parser.add_argument("-p", "--partition", metavar="PARTITION", type=str, default="long", help="Partition for download")
    parser.add_argument("-d", "--debug", metavar="DEBUG", action="store_true", help="Debug mode")
    args = parser.parse_args()

    loglevel = logging.INFO
    if args.debug:
        loglevel = logging.DEBUG
    logging.basicConfig(format="[%(levelname)s]: %(message)s", level=loglevel)

    tokens = test_alien_token()
    if not len(tokens):
        logging.info("No valid tokens found, recreating ...")
        tokens = recreate_token()
    if not len(tokens):
        logging.error("Failed generating tokens ...")
        sys.exit(1)
    cert = tokens["cert"]
    key = tokens["key"]

    handler = LaunchHandler(repo=repo, outputbase=args.outputdir, trainrun=args.trainrun, legotrain=args.legotrain)
    handler.set_token(cert, key)
    handler.set_partition_for_download(args.partition)
    handler.submit(args.year)
