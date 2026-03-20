"""Tests for notes blueprint."""
import pytest


def test_notes_index_requires_login(client):
    res = client.get('/notes/')
    assert res.status_code in (302, 401)


def test_notes_index_logged_in(logged_in_client):
    res = logged_in_client.get('/notes/')
    assert res.status_code == 200


def test_create_note(logged_in_client):
    res = logged_in_client.post('/notes/api', json={
        'title': 'Test Note', 'content': 'Hello world', 'store': 'B'
    })
    assert res.status_code == 201
    data = res.get_json()
    assert data['status'] == 'ok'
    assert 'id' in data
    return data['id']


def test_get_note(logged_in_client):
    # Create first
    res = logged_in_client.post('/notes/api', json={'title': 'Get Test', 'content': 'body'})
    note_id = res.get_json()['id']

    res = logged_in_client.get(f'/notes/api/{note_id}')
    assert res.status_code == 200
    data = res.get_json()
    assert data['title'] == 'Get Test'


def test_update_note(logged_in_client):
    res = logged_in_client.post('/notes/api', json={'title': 'Old Title', 'content': 'old'})
    note_id = res.get_json()['id']

    res = logged_in_client.put(f'/notes/api/{note_id}', json={'title': 'New Title'})
    assert res.status_code == 200
    assert res.get_json()['status'] == 'ok'

    res = logged_in_client.get(f'/notes/api/{note_id}')
    assert res.get_json()['title'] == 'New Title'


def test_delete_note(logged_in_client):
    res = logged_in_client.post('/notes/api', json={'title': 'To Delete', 'content': ''})
    note_id = res.get_json()['id']

    res = logged_in_client.delete(f'/notes/api/{note_id}')
    assert res.status_code == 200

    res = logged_in_client.get(f'/notes/api/{note_id}')
    assert res.status_code == 404


def test_list_notes(logged_in_client):
    logged_in_client.post('/notes/api', json={'title': 'List Test', 'content': ''})
    res = logged_in_client.get('/notes/api')
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, list)


def test_store_filter(logged_in_client):
    logged_in_client.post('/notes/api', json={'title': 'Store B', 'content': '', 'store': 'B'})
    logged_in_client.post('/notes/api', json={'title': 'Store C', 'content': '', 'store': 'C'})

    res = logged_in_client.get('/notes/api?store=B')
    notes = res.get_json()
    assert all(n['store'] == 'B' for n in notes)


def test_summarize_requires_admin(logged_in_client):
    res = logged_in_client.post('/notes/api', json={'title': 'Summary', 'content': 'body'})
    note_id = res.get_json()['id']
    res = logged_in_client.post(f'/notes/api/{note_id}/summarize')
    assert res.status_code == 403


def test_api_response_format(logged_in_client):
    """Contract C: API responses use {status: ok/error}."""
    res = logged_in_client.post('/notes/api', json={'title': 'T', 'content': ''})
    assert res.get_json()['status'] == 'ok'
