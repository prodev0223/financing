import os
import boto3
db_name = "fresh_odoo_10"
path = "/home/users/saurabh.gupta/.local/share/Odoo/filestore/" + db_name
bucket_name = "test-webkul-erp"
s3 = boto3.client('s3')
for r, d, f in os.walk(path):
    for file in f:
        path = os.path.join(r, file)
        fname = path.split("filestore/")[1]
        s3.upload_file(path, bucket_name, fname)
        print fname
        print path
        print "-------"
    print "---upload finish-----"

# for f in files:
#     print(f)

# https://qiita.com/hengsokvisal/items/329924dd9e3f65dd48e7
