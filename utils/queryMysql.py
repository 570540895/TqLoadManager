import logging as log
import pymysql


def query_mysql(**kwargs):
    db = pymysql.connections.Connection(**kwargs)
    cur = db.cursor()
    data = tuple()
    try:
        sql = "select j.uuid, j.name, g.startTime from job_info as j " \
            "left join gpu_consumption_info as g on j.name = g.name where g.status = 'running';"

        cur.execute(sql)
        data = cur.fetchall()
    except Exception as e:
        log.error(e)
    cur.close()
    db.close()
    return data
