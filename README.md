## Elastic Beanstalk RDS Remover

Eliminates the EB + RDS dependency by creating a new set of Elastic Beanstalk environment and standalone RDS dB instance with all the configuration settings as the old one.

Elastic Beanstalk offers users the ability to launch a RDS dB instance as part of the environment. However, as per AWS, this is not best practice for production systems since it tied the lifecycle of the RDS dB to that of the Elastic Beanstalk environment. (https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/AWSHowTo.RDS.html)

While one option to fix this is to manually create a new set of EB environment, RDS dB instance, and then configure all the settings again, this can be tedious depending on the amount of customization that was done to the EB environment. (Especially if you have a lot of environmnet variables)

This Python script will automatically create a clone of your Elastic Beanstalk environment that does not have a RDS dB attached to it. It will also create a snapshot of the old RDS dB and use it to launch a new standalone RDS dB instance. The connection parameters for this new RDS dB instance will automatically be added to the new Elastic Beanstalk environment as environment variables.

It also offers GOD mode that will do the following:

1. Enable Termination Protection of the old DB instance
2. Connect the old DB instance to the new Elastic Beanstalk standalone environment

A new DB instance or snapshot will NOT be created in GOD mode. This will make out-of-band changes to your original DB instance so it is not recommended for critical DB instances. 

Both the modes will also perform a Blue/Green deployment by doing a CNAME swap between the old and the new Elastic Beanstalk environments. 

https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/using-features.CNAMESwap.html


### Cleanup

Once the CNAME swap has been completed, it is upto the user to cleanup old resources. Terminating the old Elastic Beanstalk environment after running GOD mode will result in failed termination, and the underlying Cloud Formation stack will be in DELETE_FAILED state. You will have to manually delete the Cloud Formation stack by skipping the "AWSEBRDSDatabase" resource, and then terminate the old EB environment from the Elastic Beanstalk console.

https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/troubleshooting.html#troubleshooting-errors-delete-stack-fails


### Instructions

I have written this in Python3 and it might run into issues with Python2 especially because of the use of ruamel.yaml to modify Elastic Beanstalk saved configuration tempaltes. 

### Usage
```
1. Install ruamel.yaml with pip
2. python3 ddb.py <EB_Application_Name> <EB_Environment_Name> 

Optional Flags:
  --region : Specify the region (https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.RegionsAndAvailabilityZones.html)
  -g       : Enable GOD Mode

Example: python3 ddb.py test-app test-env -g --region us-west-2 
```
  

#### To be added:
1. Deploy the applicaiton to the new Elastic Beanstalk environment 
2. Perform cleanup of old resources
