import requests
try:
    import boto3
    import botocore
    from botocore.client import Config

except Exception as e:
    print(e)


access_key_id = ""
secret_key = ""
BUCKET_NAME = ""
KEY = ''

s3 = boto3.client('s3', region_name ='ap-south-1',config=Config(signature_version='s3v4'),aws_access_key_id=access_key_id,aws_secret_access_key=secret_key)
params = {'Bucket': BUCKET_NAME, 'Key': KEY}
url = s3.generate_presigned_url('get_object',Params=params,ExpiresIn=3600)
print (url)
