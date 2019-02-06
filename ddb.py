#!/usr/bin/env python

############################ AWS Elastic Beanstalk ############################
############################     Python 3    #################################
########################### Akshit Khanna ####################################


import boto3
import argparse
from ruamel.yaml import YAML
from ruamel.yaml.compat import StringIO
import sys
import getpass
import time


class deDB:
    def __init__(self, _env_name, _app_name, _region, _terminate_flag, _god_mode, _rds_pass ):

        self._env_name              = _env_name.strip()     
        self._app_name              = _app_name.strip()
        self._new_env               = self._env_name + "-standalone" 
        self._oenv_id               = ""
        self._terminate_flag        = _terminate_flag   #indicates if user wants to terminate old environment. Will add this later.
        self._rds_pass              = _rds_pass.strip()
        self._links                 = []
        self._template_name         = "deDB-template"
        self._updated_template      = ""
        self._stack_name            = ""
        self._rds_details           = {}
        self._new_rds_details       = {}
        self._db_new_instance_name  = _env_name.strip() + "-standalone-db" 
        self._account               = boto3.client('sts').get_caller_identity().get('Account').strip()
        self._god_mode              = _god_mode
        if _region:
            self._region            = _region          #for user specified region
        else:
            _session                = boto3.session.Session()    #retrieving region from boto3 session
            print(_session)
            self._region            = _session.region_name  
        self._s3_bucket             = "elasticbeanstalk-" + self._region + "-" + self._account


    def get_eb_details(self):
        #creates a saved configuration template for the existing environment and stores it
        #in the default EB S3 bucket at /resources/templates/applicationName
        try:
            self._oenv_id  = self.get_env_id(self._env_name,self._app_name)
            print ("Env Id is: ",self._oenv_id)
            self._stack_name = "awseb-" + self._oenv_id + "-stack"
            template_name = self._template_name + "-" + self._oenv_id
            eb   = self.client_create('elasticbeanstalk')
            response = eb.create_configuration_template(ApplicationName=self._app_name,TemplateName=template_name,EnvironmentId=self._oenv_id)
        except Exception as e:
            return e

    def get_env_id(self, env_name,app_name):   
        #did not want users to have to enter env id so this helper function retrieves it with DescribeEnvironments API
        try:
            client   = self.client_create('elasticbeanstalk')
            response = client.describe_environments(ApplicationName=app_name,EnvironmentNames=[env_name,])
            _env_id  = response['Environments'][0]['EnvironmentId'].strip()    
            return _env_id 
        except Exception as e:
            return e    

    def describe_cfn_resource(self, env_name,app_name,logical_resource_id):
        #helper function to run DesrcibeStackResource on a specific CFN stack and resource
        try:
            _env_id  = self.get_env_id(env_name,app_name)
            _stack_name = "awseb-" + _env_id + "-stack"
            client   = self.client_create('cloudformation')
            response = client.describe_stack_resource(StackName=_stack_name,LogicalResourceId=logical_resource_id)
            return response
        except Exception as e:
            return e        

    def remove_db_from_config(self):
        #Uses ruamel.yaml to remove all RDS configuration settings from the saved environment configuraiton tempalte in S3
        #and uploads the new version back to the same location in S3.
        #This newer saved configuration tempalte is then used to create a new Elastic Beanstalk environment without an atatched RDS dB
            s3 = boto3.resource('s3')

            obj = s3.Object(self._s3_bucket, ('resources/templates/' + self._app_name + '/' + self._template_name + "-" + self._oenv_id)).get()['Body'].read().decode('utf-8') 
            self._updated_template = self._template_name + "-" + self._oenv_id + '-updated'
            yaml = YAML()
            test = yaml.load(obj)
            del test["OptionSettings"]["aws:rds:dbinstance"]
            del test["Extensions"]["RDS.EBConsoleSnippet"]
            stream = StringIO()
            yaml.dump(test,stream)
            new=stream.getvalue()         

            obj = s3.Object(self._s3_bucket, ('resources/templates/' + self._app_name + '/' + self._template_name + "-" + self._oenv_id + '-updated')).put(Body=new)
            try:
                client   = self.client_create('elasticbeanstalk')
                print("Creating Elastic Beanstalk standalone environment ......")  
                response = client.create_environment(ApplicationName=self._app_name, EnvironmentName=self._new_env,Description='decoupled Env without RDS',TemplateName = self._updated_template) 
                if self._god_mode:
                    while True:
                        try:
                            response = client.describe_environment_health(
                                EnvironmentName = self._new_env,
                                AttributeNames=[
                                    'Status'
                                ]
                            )
                            _final_status = 'Ready'
                            env_status = response['Status']

                            if _final_status == env_status:
                                print('Environment Status:\t', env_status)
                                break
                            else:
                                time.sleep(10)

                        except Exception as e:
                            return e      
            except Exception as e:
                return e 


    def get_rds_details(self):
        #Populates the _rds_details dict with details like dbID and vpcID
        response = self.describe_cfn_resource(self._env_name,self._app_name,'AWSEBRDSDatabase')
        self._rds_details['db_id'] = response['StackResourceDetail']['PhysicalResourceId'].strip()
        client   = self.client_create('rds')
        describe_response = client.describe_db_instances(DBInstanceIdentifier=self._rds_details['db_id'])
        self._rds_details['vpc_id'] = describe_response['DBInstances'][0]['DBSubnetGroup']['VpcId'].strip()
        self._rds_details['endpoint'] = describe_response['DBInstances'][0]['Endpoint']['Address'].strip()
        self._rds_details['username'] = describe_response['DBInstances'][0]['MasterUsername'].strip()
        self._rds_details['db_name'] = describe_response['DBInstances'][0]['DBName'].strip()
        self._rds_details['port'] = describe_response['DBInstances'][0]['Endpoint']['Port']
        self._rds_details['security_group'] = describe_response['DBInstances'][0]['VpcSecurityGroups'][0]['VpcSecurityGroupId']        

    def enable_deletion_protection(self):
            try: 
                client     = self.client_create('rds')
                response   = client.modify_db_instance(DBInstanceIdentifier=self._rds_details['db_id'], ApplyImmediately=True, DeletionProtection=True)
            except Exception as e:
                return e


    def create_new_db(self): 
        #Creates a snapshot of the old RDS dB that is attached to the EB environment, and then uses this snapshot to create another standalone
        #RDS dB instance. 
        #Populates the _new_rds_details dict with information about the new RDS dB instance
        try:
            client            = self.client_create('rds')
            db_snapshot_name  = self._env_name + "-ddb-snapshot"
            snapshot_response = client.create_db_snapshot(DBSnapshotIdentifier=db_snapshot_name,DBInstanceIdentifier=self._rds_details['db_id'])
            snapshot_waiter   = client.get_waiter('db_snapshot_completed')
            snapshot_waiter.wait(DBSnapshotIdentifier=db_snapshot_name)
            print("restoring dB ......")
            restore_response  = client.restore_db_instance_from_db_snapshot(DBInstanceIdentifier=self._db_new_instance_name,DBSnapshotIdentifier=db_snapshot_name,Tags=[{'Key': 'string','Value': 'string'}])
            restore_waiter    = client.get_waiter('db_instance_available')
            restore_waiter.wait(DBInstanceIdentifier=self._db_new_instance_name)
            print("dB restore completed!")
            describe_response  = client.describe_db_instances(DBInstanceIdentifier=self._db_new_instance_name)
            self._new_rds_details['endpoint'] = describe_response['DBInstances'][0]['Endpoint']['Address'].strip()
            self._new_rds_details['username'] = describe_response['DBInstances'][0]['MasterUsername'].strip()
            self._new_rds_details['db_name'] = describe_response['DBInstances'][0]['DBName'].strip()
            self._new_rds_details['port'] = describe_response['DBInstances'][0]['Endpoint']['Port']
            self._new_rds_details['security_group'] = describe_response['DBInstances'][0]['VpcSecurityGroups'][0]['VpcSecurityGroupId']
        except Exception as e:
            return e         

    def client_create(self,_service):
        #helper function to create and return a service boto3 client
        try:
            client   = boto3.client(_service, self._region)      
            return client
        except Exception as e:
            return e   

    def inject_env_vars(self,_hostname,_username,_db_name,_port,_password):
        #Performs an UpdateEnvironment call on the new Elastic Beanstalk standalone environment 
        #to inject connection parameters for the new RDS dB as Environment Variables
        try:
            _env_vars = [{
                'Namespace': 'aws:elasticbeanstalk:application:environment',
                'OptionName': 'RDS_HOSTNAME',
                'Value': _hostname
            },
            {
                'Namespace': 'aws:elasticbeanstalk:application:environment',
                'OptionName': 'RDS_USERNAME',
                'Value': _username
            },
            {
                'Namespace': 'aws:elasticbeanstalk:application:environment',
                'OptionName': 'RDS_DB_NAME',
                'Value': _db_name
            },
            {
                'Namespace': 'aws:elasticbeanstalk:application:environment',
                'OptionName': 'RDS_PORT',
                'Value': _port
            },
            {
                'Namespace': 'aws:elasticbeanstalk:application:environment',
                'OptionName': 'RDS_PASSWORD',
                'Value': _password
            }]
            eb       = self.client_create('elasticbeanstalk')
            response = eb.update_environment(ApplicationName=self._app_name, EnvironmentName=self._new_env, OptionSettings=_env_vars)
            print("Updating new Elastic Beanstalk environment with RDS connection parameters....")
            while True:
                try:
                    response = eb.describe_environment_health(
                        EnvironmentName = self._new_env,
                        AttributeNames=[
                            'Status'
                        ]
                    )
                    _final_status = 'Ready'
                    env_status = response['Status']

                    if _final_status == env_status:
                        print('Environment Status:\t', env_status)
                        break
                    else:
                        time.sleep(10)
                except Exception as e:
                    return e        
        except Exception as e:
            return e               


    def configure_sg(self, _db_port, _db_security_group):
        #Grabs the id of the default AWSEBSecurityGroup of the new EB environment
        # and whitelists it for RDS traffic in the RDS Security Group of the new dB instance
            response = self.describe_cfn_resource(self._new_env, self._app_name, 'AWSEBSecurityGroup')
            _sg_groupname = response['StackResourceDetail']['PhysicalResourceId'].strip()
            _ip_permissions = [
                {
                    "IpProtocol": "tcp",
                    "FromPort": _db_port,
                    "ToPort": _db_port,
                    'UserIdGroupPairs': [{ 'GroupName': _sg_groupname }] 
                }
            ]
            ec2 = self.client_create('ec2')
            response = ec2.authorize_security_group_ingress(IpPermissions=_ip_permissions, GroupId=_db_security_group)

    def blue_green_swap(self):
        #Performs a Blue/Green CNAME swap between the old and the new environment. This might cause some issues because of DNS propagation as mentioned here: https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/using-features.CNAMESwap.html
        try:
            print("Swapping CNAMES between old and new Elastic Beanstalk environments...")
            eb       = self.client_create('elasticbeanstalk')
            response = eb.swap_environment_cnames(SourceEnvironmentName=self._env_name,DestinationEnvironmentName=self._new_env)
            print("Process completed.")

        except Exception as e:
            return e

    def migrate_database(self):
        #GOD Mode will enable termination protection on the old DB instance, and connect it to the new EB environment. It will not create a new DB instance.
        if self._god_mode:
            print('GOD Mode enabled. Termination Protection will be enabled on the DB instance and it will be connected to the new environment.')
            self.enable_deletion_protection()
            self.inject_env_vars(self._rds_details['endpoint'], self._rds_details['username'], self._rds_details['db_name'], str(self._rds_details['port']), self._rds_pass)
            self.configure_sg(self._rds_details['port'], self._rds_details['security_group'])
        
        #Without GOD Mode, a snapshot of the old DB instance will be created, which will then be used to launch a new RDS DB instance. This new DB instance will then be connected to the new EB environment.
        else:
            self.create_new_db()
            self.inject_env_vars(self._new_rds_details['endpoint'], self._new_rds_details['username'], self._new_rds_details['db_name'], str(self._new_rds_details['port']), self._rds_pass)
            self.configure_sg(self._new_rds_details['port'], self._new_rds_details['security_group'])

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("env_name", help="Enter the name of the Elastic Beanstalk environment")
    parser.add_argument("app_name", help="Enter the name of the Elastic Beanstalk application") 
    parser.add_argument('--region', help="Use this flag to specify the region")    
    parser.add_argument('-t', help="Use this flag to terminate the old environment", action='store_true')
    parser.add_argument('-g', help="Use this flag to enable GOD mode", action='store_true')
    parser.parse_args()
    args = parser.parse_args()
    rds_pass = getpass.getpass(prompt='Enter a password for the standalone dB instance:') 
    parserObject = deDB(args.env_name, args.app_name, args.region, args.t, args.g, rds_pass)
    parserObject.get_eb_details()
    parserObject.remove_db_from_config()
    parserObject.get_rds_details()
    parserObject.migrate_database()
    parserObject.blue_green_swap()