#! /bin/bash

WORKDIR=$1
DATAFILE=$2
MCFILE=$3
SYSVAR=$4
RADIUS=$5
UNFOLDINGMACRO=$6

ALIENV=`which alienv`
eval `$ALIENV --no-refresh printenv AliPhysics/latest`

SOURCEDIR=/software/markus/alice/SubstructureAnalysis/unfolding/1D
UNFOLDINGMETHOD=
if [ "x$(echo $UNFOLDINGMACRO | grep SVD)" != "x" ]; then
    UNFOLDINGMETHOD=SVD
else if [ "x$(echo $UNFOLDINGMACRO | grep Bayes)" != "x" ]; then
    UNFOLDINGMETHOD=Bayes
else
    echo Unknown unfolding method, skipping ...
    exit 1
fi
SCRIPT=$SOURCEDIR/$UNFOLDINGMETHOD/$UNFOLDINGMACRO
if [ ! -f $SCRIPT ]; then
    echo Unfolding macro does not exist, skipping ...
    exit 1
fi
echo "Using unfolding macro $SCRIPT"

if [ ! -d $WORKDIR ]; then mkdir -p $WORKDIR; fi
cd $WORKDIR
cmd=$(printf "root -l -b -q \'%s(\"%s\", \"%s\", \"%s\", %d)\' &> %s/unfolding_R%02d.log" $SCRIPT $DATAFILE $MCFILE $SYSVAR $RADIUS $WORKDIR $RADIUS)
echo Running command: $cmd
eval $cmd