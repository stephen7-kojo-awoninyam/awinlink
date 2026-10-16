"""Read-only diagnostics for the explicitly created loopback audit resources."""
import psycopg2
import redis
import urllib.request

print('Probing audit PostgreSQL', flush=True)
try:
    connection = psycopg2.connect(host='127.0.0.1', port=55432, user='vc_audit', dbname='postgres', connect_timeout=3)
    with connection.cursor() as cursor:
        cursor.execute("SELECT datname,state,wait_event_type,wait_event FROM pg_stat_activity WHERE datname LIKE 'awinlink_audit%'")
        print(cursor.fetchall(), flush=True)
    connection.close()
except Exception as error:
    print(type(error).__name__, str(error), flush=True)
print('Probing audit Redis', flush=True)
try:
    print(redis.Redis(host='127.0.0.1', port=16379, socket_connect_timeout=3, socket_timeout=3).ping(), flush=True)
except Exception as error:
    print(type(error).__name__, str(error), flush=True)
for port in [18765, 18766]:
    print('Probing audit worker', port, flush=True)
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/learning/classrooms/', timeout=5) as response:
            print(response.status, flush=True)
    except Exception as error:
        print(type(error).__name__, str(error), flush=True)
