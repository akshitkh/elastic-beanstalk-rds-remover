## Elastic Beanstalk RDS Remover

Eliminates the EB + RDS dependency by creating a new set of Elastic Beanstalk environment and standalone RDS dB instance with all the configuration settings as the old one.

Elastic Beanstalk offers users the ability to launch a RDS dB instance as part of the environment. However, as per AWS, this is not best practice for production systems since it tied the lifecycle of the RDS dB to thatr of the Elastic Beanstalk environment. (https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/AWSHowTo.RDS.html)

While one option to fix this is to manually create a new set of EB environment, RDS dB instance, and then configure all the settings again, this can be tedious depending on the amount of customization that was done to the EB environment. (Especially if you have a lot of environmnet variables)

This Python script will automatically create a clone of your Elastic Beanstalk environment that does not have a RDS dB attached to it. It will also create a snapshot of the old RDS dB and use it to launch a new standalone RDS dB instance. The connection parameters for this new RDS dB instance will automatically be added to the new Elastic Beanstalk environment as environment variables.


### Instructions

I have written this in Python3 and it might run into issues with Python2 especially because of the use of ruamel.yaml to modify Elastic Beanstalk saved configuration tempaltes. 

### Usage
```
1. Install ruamel.yaml with pip
2. python3 ddb.py <EB_Application_Name> <EB_Environment_Name> 

Optional Flags:
  --region : Specify the region (https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.RegionsAndAvailabilityZones.html)
```
  

#### To be added:
1. Ability to perform a CNAME swap between the old and the new Elastic Beanstalk environment
2. Deploy the applicaiton to the new Elastic Beanstalk environment 
