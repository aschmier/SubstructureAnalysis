#! /bin/bash

CONFIGDIR=$1
OUTPUTBASE=$2

CHUNK=$(printf "%02d" $SLURM_ARRAY_TASK_ID)
OUTPUTDIR=$OUTPUTBASE/$CHUNK
if [ ! -d $OUTPUTDIR ]; then mkdir -p $OUTPUTDIR; fi
cd $OUTPUTDIR
cp CONFIGDIR/lego_train* $OUTPUTDIR

ALIENV=`which alienv`
eval `$ALIENV --no-refresh printenv AliPhysics/latest legotrain_helpers/latest`
eval `$ALIENV list

export ALIEN_PROC_ID=$SLURM_JOB_ID
cmd=$(runtraintest &> train.log)
eval $cmd
rm -rf lego_train*