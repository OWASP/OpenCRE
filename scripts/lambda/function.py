import boto3
import json
import os
from pprint import pprint
import yaml
import json

def filter_cre_id(cre_file,cre_id):
    res = []
    cres = ""
    try:
        cres = list(yaml.safe_load_all(cre_file))[0].values()
    except Exception as ex:
        pprint(ex) # probably malformed file
    for thing in cres:
        for cre in thing:
            if cre_id in cre.get('CRE'):
                res.append(cre)
    return res

def filter_all(cre_file):
    res = []
    cres = ""
    try:
        cres = list(yaml.safe_load_all(cre_file))[0].values()
    except Exception as ex:
        pprint(ex) # probably malformed file
    for thing in cres:
        for cre in thing:
                res.append(cre)
    return res
    
def filter_cre_contains_tag(cre_file, tag):
    res = []
    cres = ""
    try:
        cres = list(yaml.safe_load_all(cre_file))[0].values()
    except Exception as ex:
        pprint(ex) # probably malformed file
    for thing in cres:
        for cre in thing:
            if tag in cre['metadata']['tags']:
                res.append(cre)
    return res

def cre_to_json_str(cre):
    res = json.dumps(cre)
    return res or ""

def list_files(bucket):
    s3 = boto3.client('s3')
    objects = s3.list_objects_v2(Bucket=bucket)
    return objects

def get_file(bucket,file_obj):
    s3_res = boto3.resource('s3')
    return s3_res.Object(bucket,file_obj['Key']).get()['Body'].read().decode()

def lambda_handler(event, context):
    ret = {
             'statusCode': 200,
             'body':"",
         }
    # return ret
    cres = []
    try:
        cre_id=event.get("queryStringParameters").get('cre')
        tag=event.get("queryStringParameters").get('tag')
        # return ret
        bucket = os.environ.get("bucket_name")
        objects = list_files(bucket)
        for file_obj in objects.get('Contents'):
            obj=[]
            cre_file = get_file(bucket,file_obj)
            if cre_id:
                print("Filtering By CREID")
                obj = filter_cre_id(cre_file,cre_id)
            elif tag:
                print("Filtering By Tag")
                obj = filter_cre_contains_tag(cre_file,tag)
            # else:
            #     obj=filter_all(cre_file)
            if obj:
                cres.extend(obj)
        return_obj = []
        for cre in cres:
            return_obj.append(cre)
        ret['body'] = ret['body'] + cre_to_json_str(return_obj)
    except Exception as ex:
        ret['body'] = str(ex)
        
    return ret
