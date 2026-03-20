"""Tests for auth blueprint."""
import pytest
import json


def test_register_requires_admin(client):
    """Unauthenticated users cannot register."""
    res = client.post('/auth/register', json={'username': 'newuser_reg', 'pin': '5678'})
    assert res.status_code in (401, 302, 403)


def test_register_non_admin_forbidden(logged_in_client):
    """Regular (non-admin) users get 403 on register."""
    res = logged_in_client.post('/auth/register', json={'username': 'newuser_reg', 'pin': '5678'})
    assert res.status_code == 403


def test_register_success(logged_in_admin_client):
    res = logged_in_admin_client.post('/auth/register', json={'username': 'newuser_reg', 'pin': '5678'})
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'ok'
    assert 'user_id' in data


def test_register_duplicate(logged_in_admin_client):
    logged_in_admin_client.post('/auth/register', json={'username': 'dupuser', 'pin': '1111'})
    res = logged_in_admin_client.post('/auth/register', json={'username': 'dupuser', 'pin': '2222'})
    assert res.status_code == 409


def test_register_missing_fields(logged_in_admin_client):
    res = logged_in_admin_client.post('/auth/register', json={'username': '', 'pin': ''})
    assert res.status_code == 400


def test_login_success(client, test_user):
    """test_user has face enrolled → must provide face_image."""
    fake_b64 = 'data:image/jpeg;base64,/9j/4AAQSkZJRg=='
    res = client.post('/auth/login', json={
        'username': test_user.username, 'pin': '1234', 'face_image': fake_b64
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'ok'
    assert 'redirect' in data


def test_login_face_required(client, test_user):
    """test_user has face enrolled → omitting face_image returns face_required."""
    res = client.post('/auth/login', json={'username': test_user.username, 'pin': '1234'})
    assert res.status_code == 200
    assert res.get_json()['status'] == 'face_required'


def test_login_no_face_redirects_to_enroll(client, admin_user):
    """admin_user has no face → server logs in and returns need_face_enroll."""
    res = client.post('/auth/login', json={'username': admin_user.username, 'pin': '0000'})
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'need_face_enroll'
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


# ── Admin create user endpoint ────────────────────────────────────────────────

def test_admin_create_user_success(logged_in_admin_client):
    fake_b64 = 'data:image/jpeg;base64,/9j/4AAQSkZJRg=='
    res = logged_in_admin_client.post('/admin/users/create', json={
        'username': 'employee01', 'pin': '2468', 'face_image': fake_b64
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'ok'
    assert data['username'] == 'employee01'
    assert 'user_id' in data


def test_admin_create_user_missing_fields(logged_in_admin_client):
    res = logged_in_admin_client.post('/admin/users/create', json={'username': '', 'pin': ''})
    assert res.status_code == 400


def test_admin_create_user_duplicate(logged_in_admin_client):
    logged_in_admin_client.post('/admin/users/create', json={'username': 'emp_dup', 'pin': '1111'})
    res = logged_in_admin_client.post('/admin/users/create', json={'username': 'emp_dup', 'pin': '2222'})
    assert res.status_code == 409


def test_admin_create_user_requires_admin(logged_in_client):
    res = logged_in_client.post('/admin/users/create', json={'username': 'emp_x', 'pin': '1234'})
    assert res.status_code == 403


def test_app_mode_notes_redirect(app):
    """APP_MODE=notes → root redirects to /auth/login."""
    import os
    os.environ['APP_MODE'] = 'notes'
    try:
        with app.test_client() as c:
            res = c.get('/', follow_redirects=False)
            assert res.status_code == 302
            assert '/auth/login' in res.headers['Location']
    finally:
        del os.environ['APP_MODE']


def test_app_mode_default_weather_redirect(app):
    """No APP_MODE → root redirects to weather."""
    import os
    os.environ.pop('APP_MODE', None)
    with app.test_client() as c:
        res = c.get('/', follow_redirects=False)
        assert res.status_code == 302
        assert '/weather' in res.headers['Location']
