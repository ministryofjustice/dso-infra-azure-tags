#!/bin/bash

SOURCE_DIR=~/Downloads
SOURCE_SUBFILE="Azure DSO - subscriptionOverview.tsv"
SOURCE_RGFILE="Azure DSO - rgstags.tsv"
SOURCE_RESFILE="Azure DSO - resourcestags.tsv"
SUBFILE=inherit.AzureDSO.subscriptionOverview.txt
RGFILE=inherit.AzureDSO.rgstags.txt
RESFILE=inherit.AzureDSO.resourcestags.txt

swap() {
  gsed -i "1 s/$1/$2/" ${@:3}
}

filter() {
  [ ! -d $1 ] && mkdir -p $1 
  head -1 $2 > $1/$4
  grep -h "$3" $2 >> $1/$4
}

filter_id() {
  [ ! -d $1 ] && mkdir -p $1
  head -1 $2 | cut -d\| -f1 > $1/$4
  grep -h "$3" $2 | cut -d\| -f1 >> $1/$4
}

filter_all() {
  filter NOMSProduction1/service_app_component_env_desc $1 1d95dcda-65b2-4273-81df-eb979c6b547b $1
  filter NOMSDevTestEnvironments/service_app_component_env_desc $1 b1f3cebb-4988-4ff9-9259-f02ad7744fcb $1
  filter NOMSDigitalStudioProduction1/service_app_env_desc $1 a5ddf257-3b21-4ba9-a28c-ab30f751b383 $1
  filter P-NOMISDSOdevelopment/service_app_env_desc $1 22b0ff4c-6d78-4964-ac2a-b7cda4a58755 $1
  filter P-NOMISnonproduction/service_app_env_desc $1 b9aa011b-7a41-46e1-8088-4a32e4bd92e0 $1
  filter P-NOMISproduction/service_app_env_desc $1 4bdc3aa7-2dbe-4031-aaa1-20456ed7b221 $1
  filter DigitalStudioDevTestEnvironments/service_app_env_desc $1 c27cfedb-f5e9-45e6-9642-0fad1a5c94e7 $1
}

filter_all_ids() {
  filter_id NOMSProduction1 $1 1d95dcda-65b2-4273-81df-eb979c6b547b $2
  filter_id NOMSDevTestEnvironments $1 b1f3cebb-4988-4ff9-9259-f02ad7744fcb $2
  filter_id NOMSDigitalStudioProduction1 $1 a5ddf257-3b21-4ba9-a28c-ab30f751b383 $2
  filter_id P-NOMISDSOdevelopment $1 22b0ff4c-6d78-4964-ac2a-b7cda4a58755 $2
  filter_id P-NOMISnonproduction $1 b9aa011b-7a41-46e1-8088-4a32e4bd92e0 $2
  filter_id P-NOMISproduction $1 4bdc3aa7-2dbe-4031-aaa1-20456ed7b221 $2
  filter_id DigitalStudioDevTestEnvironments $1 c27cfedb-f5e9-45e6-9642-0fad1a5c94e7 $2
}

# Use Azure DSO sheet and save as tsv the vmanalysis and rgtags tabs
if [[ -e $SOURCE_DIR/"$SOURCE_SUBFILE" ]]; then
  cat $SOURCE_DIR/"$SOURCE_SUBFILE" | cut  -f1,7,8,10 | sed -e $'s/\t/|/g' | grep -v '||' > $SUBFILE
  dos2unix $SUBFILE
  swap 'Subscription Id' 'id' $SUBFILE
  gsed -i '2,$ s/^/\/subscriptions\//'  $SUBFILE
  filter_all $SUBFILE $SUBFILE
  filter_all_ids $SUBFILE subscription.txt
else
  echo $SOURCE_DIR/"$SOURCE_SUBFILE" does not exist
fi

if [[ -e $SOURCE_DIR/"$SOURCE_RGFILE" ]]; then
  cat $SOURCE_DIR/"$SOURCE_RGFILE" | cut -f1,2,3,4,5 | sed -e $'s/\t/|/g' | grep -v '|||' > $RGFILE
  dos2unix $RGFILE
  filter_all $RGFILE
else
  echo $SOURCE_DIR/"$SOURCE_RGFILE" does not exist
fi

if [[ -e $SOURCE_DIR/"$SOURCE_RESFILE" ]]; then
  cat $SOURCE_DIR/"$SOURCE_RESFILE" | cut  -f2,10,11,12,13,14 | sed -e $'s/\t/|/g' | grep -v '||||' > $RESFILE
  dos2unix $RESFILE
  filter_all $RESFILE
else
  echo $SOURCE_DIR/"$SOURCE_SRESFILE" does not exist
fi

rm -f $SUBFILE
rm -f $RESFILE
rm -f $RGFILE

