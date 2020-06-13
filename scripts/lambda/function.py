import boto3
import json
import os
from pprint import pprint
import yaml
import json

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
    return res

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
    cres = []
    try:
        tag=event.get('tag') or 'crypto'
        bucket = os.environ.get("bucket_name")
        objects = list_files(bucket)
        for file_obj in objects['Contents']:
            cre_file = get_file(bucket,file_obj)
            obj = filter_cre_contains_tag(cre_file,tag)
            if obj is not None:
                cres.extend(obj)
        for cre in cres:
            ret['body'] = ret['body'] + cre_to_json_str(cre)
    except Exception as ex:
        ret['body'] = str(ex)
    return ret
