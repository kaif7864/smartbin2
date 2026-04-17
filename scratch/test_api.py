import requests

url = "https://127.0.0.1:8000/api/reading"
files = {
    'image': ('test.jpg', b'fake image data', 'image/jpeg')
}
data = {
    'weight': 100.5,
    'userid': 'test_user',
    'binid': 'test_bin'
}

try:
    response = requests.post(url, data=data, files=files)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
except Exception as e:
    print(f"Error: {e}")
