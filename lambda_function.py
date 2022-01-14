import boto3
import botocore
import logging

from urllib import parse

logger = logging.getLogger(__name__)
logger.setLevel('INFO')


# The copy() method is not available on boto3.client. 
# We use the client from the resource instead.
s3_client = boto3.resource('s3').meta.client


class SkipException(Exception):
    pass


def enable_bucket_key_for(bucket_name, obj_key):
    """
    Enable bucket key (if needed) on a given object.

    :param bucket_name: The name of the bucket where the object is located
    :param obj_key: The object key to validate
    """
    logger.info(f'Enabling bucket key for object key: {obj_key}.')

    try:
        obj_head = s3_client.head_object(Bucket=bucket_name, Key=obj_key)
    except botocore.exceptions.ClientError as e:
        raise SkipException(f'Error looking for {obj_key}: {e}')

    validate_file(obj_key, obj_head)

    copy_source = {
        'Bucket': bucket_name,
        'Key': obj_key,
    }

    # Enable the bucket key, while re-applying the same key
    extra_args = {
        'ServerSideEncryption': 'aws:kms',
        'SSEKMSKeyId': obj_head.get('SSEKMSKeyId'),
        'BucketKeyEnabled': True,
    }

    # StorageClass parameters are not forwarded by default so we do it manually
    storage_class = obj_head.get('StorageClass')
    if storage_class is not None:
        extra_args['StorageClass'] = storage_class

    config = boto3.s3.transfer.TransferConfig(use_threads=False)

    s3_client.copy(
        copy_source,
        bucket_name,
        obj_key,
        ExtraArgs=extra_args,
        Config=config
    )

def validate_file(obj_key, obj_head):
    """
    Ensures the bucket key should be enabled for that object.

    :param obj_key: The object key to validate
    :param head_object: The head_object's response for the object
    """
    if obj_head.get('ContentLength') == 0:
        raise SkipException(f'{obj_key} is not a file')
    
    if obj_head.get('ServerSideEncryption') != 'aws:kms':
        raise SkipException(f'{obj_key} is not KMS encrypted')
    
    if obj_head.get('ArchiveStatus') is not None:
        raise SkipException(f'{obj_key} is archived')

    if obj_head.get('BucketKeyEnabled'):
        raise SkipException(f'{obj_key} already has the bucket key enabled')


def lambda_handler(event, context):
    """
    Enable bucket key (if needed) on a given object.

    :param event: The S3 batch event that contains the ID of the delete marker
                  to remove.
    :param context: Context about the event.
    :return: A result structure that Amazon S3 uses to interpret the result of
             the operation. When the result code is TemporaryFailure, S3
             retries the operation.
    """
    results = []
    result_code = None
    result_string = None

    task = event['tasks'][0]
    obj_key = parse.unquote(task['s3Key'], encoding='utf-8')
    bucket_name = task['s3BucketArn'].split(':')[-1]

    try:
        enable_bucket_key_for(bucket_name, obj_key)

        result_code = 'Succeeded'
        result_string = f'Successfully enabled bucket key for {obj_key}.'
        logger.info(result_string)
    except SkipException as error:
        result_code = 'Succeeded'
        result_string = f'Skipped key: {obj_key} - {error}'
        logger.warning(result_string)
    except Exception as error:
        result_code = 'PermanentFailure'
        result_string = str(error)
        logger.exception(error)
    finally:
        results.append({
            'taskId': task['taskId'],
            'resultCode': result_code,
            'resultString': result_string
        })

    return {
        'invocationSchemaVersion': event['invocationSchemaVersion'],
        'treatMissingKeysAs': 'PermanentFailure',
        'invocationId': event['invocationId'],
        'results': results
    }