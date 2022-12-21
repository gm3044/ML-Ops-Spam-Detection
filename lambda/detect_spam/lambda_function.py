import json
import boto3
import email
import re
import os
from sms_spam_classifier_utilities import one_hot_encode
from sms_spam_classifier_utilities import vectorize_sequences
from botocore.exceptions import ClientError

def sendEmail(message, emailTo, subject):
    ses_client = boto3.client("ses", region_name="us-east-1")
    CHARSET = "UTF-8"

    try:
        #Provide the contents of the email.
        response = ses_client.send_email(
            Destination={
                'ToAddresses': [
                    emailTo,
                ],
            },
            Message={
                'Body': {
                    'Text': {
                        'Charset': CHARSET,
                        'Data': message,
                    },
                },
                'Subject': {
                    'Charset': CHARSET,
                    'Data': subject,
                },
            },
            Source="asurashen8@gmail.com",
        )
    # Display an error if something goes wrong.
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        print("Email sent! Message ID:")
        print(response['MessageId'])


def lambda_handler(event, context):
   
    ENDPOINT_NAME = os.environ['ENDPOINT_NAME']
    
    objectKey = event["Records"][0]["s3"]["object"]["key"]
    s3 = boto3.resource('s3')
    bucket = 'emailstore-86'
    obj = s3.Object(bucket, objectKey)
    
    msg = obj.get()['Body'].read().decode('utf-8')
    msg = email.message_from_string(msg)
    receive_date = msg['Date']
    receive_subject = msg['Subject']
    receive_from = msg['from']
    receive_body = ''
    if msg.is_multipart():
        for res in [k.get_payload() for k in msg.walk() if k.get_content_type() == 'text/plain']:
            receive_body = res
    else:
        receive_body = msg.get_payload()

  
    # preprocess fro training
    messages = re.sub('[ \n\r\t\f]+', ' ', receive_body).replace('*', '').strip()
    vocabulary_length = 9013
    messages = [messages]
    one_hot_messages = one_hot_encode(messages, vocabulary_length)
    encoded_messages = vectorize_sequences(one_hot_messages, vocabulary_length)
    payload = json.dumps(encoded_messages.tolist())

    # Connect Sagemaker
    client = boto3.client('sagemaker-runtime')
    response = client.invoke_endpoint(
    EndpointName=ENDPOINT_NAME,
    Body=payload,
    ContentType='application/json')

    # Handle Result
    result = json.loads(response['Body'].read().decode())
    label = result['predicted_label'][0][0]
    pred_prob = result['predicted_probability'][0][0]
    
    print('result is here')
    print(result)
    

    classification = 'ham'
    if label == 0:
        classification = 'ham'
        confidence_score = (1 - pred_prob)*100
    else:
        classification = 'spam'
        confidence_score = pred_prob*100

  
    SUBJECT = 'Spam detection result of ' + receive_subject
    BODY_TEXT = "We received your email sent at {} with the subject {}.\n\n" \
                "Here is a 240 character sample of the email body:\n\n{}\n\n" \
                "The email was categorized as {} with a {}% " \
                "confidence.".format(receive_date, SUBJECT, receive_body, classification, confidence_score)
    print(SUBJECT)
    print(BODY_TEXT)
    print(receive_from)
    sendEmail(BODY_TEXT, receive_from, SUBJECT)

 
    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }
