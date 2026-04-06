import requests

# Fill in your 3 values here:
CLIENT_ID = "221376"
CLIENT_SECRET = "44b06fd3847d6f365aafc24ef7628dfbeab44531"
CODE = "80cdb403cc2e81ebaf660f83d3015db8d98acc7c"

url = "https://www.strava.com/oauth/token"
payload = {
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "code": CODE,
    "grant_type": "authorization_code"
}

response = requests.post(url, data=payload)
data = response.json()

print("\n🎉 SUCCESS! Here is your permanent Refresh Token:")
print("REFRESH_TOKEN:", data.get("refresh_token"))