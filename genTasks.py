from datetime import datetime
import logging
import json
import multiprocessing
import time
import pandas as pd
import sched
from utils import preProcess, sendRequest, queryMysql
import pymysql

# log config
log_file = r'./logs/test.log'
logging.basicConfig(filename=log_file, level=logging.DEBUG)
log = logging.getLogger(__name__)

# generate tasks params
csv_file = './data/data.csv'
sorted_csv_file = './data/sorted_data.csv'
gen_api_path = '/api/model/trainjobs'
time_compress = 30
start_interval = 60

# stop tasks params
stop_api_path = '/api/model/trainjobs/{}/stop'

# config params
tq_config_file = './config/tq-config.json'
mysql_config_file = './config/mysql-config.json'
headers_template_file = './template/request_headers_template.json'
body_template_file = './template/request_body_template.json'

# read config files
with open(tq_config_file, 'r') as fp:
    tq_config_dict = json.load(fp)
    tq_host = tq_config_dict['host']
    tq_port = tq_config_dict['port']
    compute_spec_list = tq_config_dict['computeSpecList']
    # tq_user_name = tq_config_dict['tqUserName']
    fp.close()
base_url = 'http://' + tq_host + ':' + tq_port

with open(mysql_config_file, 'r') as fp:
    mysql_config_dict = json.load(fp)
    mysql_kwargs = {
        'host': mysql_config_dict['host'],
        'port': mysql_config_dict['port'],
        'user': mysql_config_dict['user'],
        'password': mysql_config_dict['password'],
        'database': mysql_config_dict['database'],
        'charset': mysql_config_dict['charset']
    }
    fp.close()


# generate tq tasks
def gen_tasks(m_duration, s_dict):
    request_url = base_url + gen_api_path

    # sort csv file
    preProcess.sort_csv_file(csv_file, sorted_csv_file)

    m_duration.value = preProcess.get_min_duration(sorted_csv_file)

    # read template files
    with open(headers_template_file, 'r') as fp:
        headers_json = json.load(fp)
        fp.close()

    with open(body_template_file, 'r') as fp:
        body_json = json.load(fp)
        fp.close()

    # create tasks according to csv file
    df = pd.read_csv(sorted_csv_file)

    csv_start_time = df['createDate'][0]
    exec_start_time = int(time.time()) + start_interval

    scheduler = sched.scheduler(time.time, time.sleep)

    for index, row in df.iterrows():
        task_name = 'tq_test_' + str(index)
        create_date = row['createDate']
        exec_duration = max(int(row['exec_duration'] / time_compress), 1)
        gpu_num = row['gpu_num']
        worker_num = row['worker_num']

        body_json['name'] = task_name
        if gpu_num == 4:
            body_json['resource']['projectUuid'] = compute_spec_list[0]['projectUuid']
            body_json['resource']['computeSpecUuid'] = compute_spec_list[0]['computeSpecUuid']
            body_json['resource']['computeSpecName'] = compute_spec_list[0]['computeSpecName']
        elif gpu_num == 8:
            body_json['resource']['projectUuid'] = compute_spec_list[1]['projectUuid']
            body_json['resource']['computeSpecUuid'] = compute_spec_list[1]['computeSpecUuid']
            body_json['resource']['computeSpecName'] = compute_spec_list[1]['computeSpecName']
        else:
            log.error('generate tasks error: index: {} gpu_num is not 4 or 8.'.format(index))
            continue
        body_json['resource']['workerNum'] = worker_num

        time_interval = int((create_date - csv_start_time) / time_compress)
        scheduler.enter(exec_start_time+time_interval-int(time.time()), 0,
                        sendRequest.send_request, (request_url, 'post', headers_json, body_json))
        s_dict[task_name] = exec_duration
    scheduler.run()


# stop tq tasks
def stop_tasks(m_duration, s_dict):
    # read config json
    with open(headers_template_file, 'r') as fp:
        headers_json = json.load(fp)
        fp.close()

    request_url = base_url + stop_api_path

    while True:
        scheduler = sched.scheduler(time.time, time.sleep)
        mysql_rows = queryMysql.query_mysql(**mysql_kwargs)
        for row in mysql_rows:
            uuid = row[0]
            task_name = row[1]
            start_time = int(datetime.timestamp(row[2]))
            now = int(time.time())
            if task_name not in s_dict:
                log.error('Task: {} not found while stopping task'.format(task_name))
                continue
            if s_dict['task_name'] == 0:
                continue
            request_url = request_url.format(uuid)
            scheduler.enter(start_time+s_dict[task_name]-now, 0,
                            sendRequest.send_request, (request_url, 'put', headers_json, {}))
        if not scheduler.empty():
            scheduler.run()
        time.sleep(max(m_duration-1, 1))


if __name__ == '__main__':
    with multiprocessing.Manager() as manager:
        min_duration = multiprocessing.Value('i', 10)
        shared_dict = manager.dict()
        p1 = multiprocessing.Process(target=gen_tasks, args=(min_duration, shared_dict, ))
        p2 = multiprocessing.Process(target=stop_tasks, args=(min_duration, shared_dict, ))
        p1.start()
        p2.start()