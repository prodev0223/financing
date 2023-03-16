try:
    import boto3
    import botocore
except Exception as e:
    print(e)


access_key_id = "xxxxxxxxxxxx"
secret_key = "xxxxxxxxxxxxx"
BUCKET_NAME = "xxxxx"

s3 = boto3.resource('s3', aws_access_key_id=access_key_id, aws_secret_access_key=secret_key)
print (s3)
for bucket in s3.buckets.all():
    print(bucket.name)
#
data = open('/home/users/Wallpapers/Home - Website localhost.jpg', 'rb')
print (data)
# result = s3.Bucket(BUCKET_NAME).put_object(Key='test.jpg', Body=data,ACL='public-read',ContentType="image/jpeg")
# print (dir(result))
#
# try:
#     down = s3.Bucket(BUCKET_NAME).download_file('test.jpg', 'my_local_image.jpg')
#     print(down)
# except botocore.exceptions.ClientError as e:
#     if e.response['Error']['Code'] == "404":
#         print("The object does not exist.")
#     else:
#         raise
# s3 = boto3.client('s3')
bucket_location = s3.meta.client.get_bucket_location(Bucket=BUCKET_NAME)
location_constraint = bucket_location.get('LocationConstraint')
print (location_constraint)
s3 = boto3.client('s3')
url = '{}/{}/{}'.format(s3.meta.endpoint_url.replace("s3",
                                                     "s3.ap-south-1"), BUCKET_NAME, "test.jpg")
print(url)

# https://s3.ap-south-1.amazonaws.com/odoo-test-mohit/test.jpg
# https://s3.amazonaws.com/odoo-test-mohit/test.jpg
