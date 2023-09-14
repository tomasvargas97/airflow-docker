from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from datetime import datetime
import requests
import psycopg2
import json
import spotipy
from spotipy import SpotifyClientCredentials
from tokens import tokens

SPOTIFY_CLIENT_ID = tokens['SPOTIFY_CLIENT_ID']
SPOTIFY_CLIENT_SECRET = tokens['SPOTIFY_CLIENT_SECRET']


PG_HOST = 'postgres'
PG_PORT = 5432
PG_DB = 'airflow'
PG_USER = 'airflow'
PG_PASSWORD = 'airflow'


default_args = {
    'owner': 'your_name',
    'depends_on_past': False,
    'start_date': datetime(2023, 1, 1),
    'retries': 1,
}

dag = DAG('spotify_top_50_us_to_local_postgres', default_args=default_args, schedule_interval=None)

def generate_access_token():
    client_credentials_manager = SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET
    )
    sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)
    token_info = sp.client_credentials_manager.get_access_token()
    print(token_info)
    return token_info

generate_token_task = PythonOperator(
    task_id='generate_access_token',
    python_callable=generate_access_token,
    provide_context=True,
    dag=dag,
)


def extract_top_50_us(**kwargs):
    access_token = kwargs['ti'].xcom_pull(task_ids='generate_access_token')

    # Set up the authorization header with the access token
    headers = {
        'Authorization': f'Bearer {access_token}',
    }

    # Make the API request to fetch the top 50 tracks in the US
    params = {
        'country': 'US',
        'limit': 50,
    }

    response = requests.get('https://api.spotify.com/v1/artists/06HL4z0CvFAxyc27GXpf02/top-tracks', params=params, headers=headers)

    if response.status_code == 200:
        top_tracks = response.json()
        return top_tracks
    else:
        print(f'Error: {response.status_code} - {response.text}')


extract_task = PythonOperator(
    task_id='extract_top_50_us',
    python_callable=extract_top_50_us,
    provide_context=True,
    dag=dag,
)


def load_to_local_postgres(**kwargs):
    top_tracks = kwargs['ti'].xcom_pull(task_ids='extract_top_50_us')

    # Establish a connection to the local PostgreSQL database
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DB,
        user=PG_USER,
        password=PG_PASSWORD,
    )

    cursor = conn.cursor()

    # Create a table to store the top tracks
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS top_tracks (
        track_name TEXT,
        artist_name TEXT,
        album_name TEXT
    );
    """
    cursor.execute(create_table_sql)

    # Insert the top tracks into the local PostgreSQL table
    for track in top_tracks['tracks']:
        insert_sql = """
        INSERT INTO top_tracks (track_name, artist_name, album_name)
        VALUES (%s, %s, %s);
        """
        cursor.execute(insert_sql, (track['name'], track['artists'][0]['name'], track['album']['name']))

    # Commit and close the database connection
    conn.commit()
    conn.close()


load_task = PythonOperator(
    task_id='load_to_local_postgres',
    python_callable=load_to_local_postgres,
    provide_context=True,
    dag=dag,
)

generate_token_task >> extract_task >> load_task