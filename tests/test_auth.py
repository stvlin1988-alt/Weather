"""Tests for auth blueprint."""
import pytest
import json


def test_register_success(client):
    res = client.post('/auth/register', json={'username': 'newuser_reg', 'pin': '5678'})
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'ok'
    assert 'user_id' in data


def test_register_duplicate(client):
    client.post('/auth/register', json={'username': 'dupuser', 'pin': '1111'})
    res = client.post('/auth/register', json={'username': 'dupuser', 'pin': '2222'})
    assert res.status_code == 409


def test_register_missing_fields(client):
    res = client.post('/auth/register', json={'username': '', 'pin': ''})
    assert res.status_code == 400


def test_login_success(client, test_user):
    res = client.post('/auth/login', json={'username': test_user.username, 'pin': '1234'})
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'ok'
    assert 'redirect' in data


def test_login_wrong_pin(client, test_user):
    res = client.post('/auth/login', json={'username': test_user.username, 'pin': '9999'})
    assert res.status_code == 401
    assert res.get_json()['status'] == 'wrong_password'


def test_login_page_get(client):
    res = client.get('/auth/login')
    assert res.status_code == 200


def test_verify_success(client, test_user):
    """Face + PIN verify — server sets session."""
    fake_b64 = 'data:image/jpeg;base64,/9j/4AAQSkZJRg=='  # minimal JPEG header
    res = client.post('/auth/verify', json={'pin': '1234', 'face_image': fake_b64})
    data = res.get_json()
    assert data['status'] == 'ok'


def test_verify_wrong_pin(client, test_user):
    fake_b64 = 'data:image/jpeg;base64,/9j/4AAQSkZJRg=='
    res = client.post('/auth/verify', json={'pin': '9999', 'face_image': fake_b64})
    data = res.get_json()
    assert data['status'] == 'wrong_password'


def test_verify_no_face_image(client, test_user):
    res = client.post('/auth/verify', json={'pin': '1234'})
    data = res.get_json()
    assert data['status'] == 'face_mismatch'


def test_silent_redirect_requires_login(client):
    res = client.get('/auth/s/r')
    assert res.status_code in (302, 401)


def test_logout(logged_in_client):
    res = logged_in_client.get('/auth/logout', follow_redirects=False)
    assert res.status_code == 302
