# {k: new_dict[k] for k in new_dict if k in old_dict and new_dict[k] > old_dict[k]}
import requests

def check_user_is_valide(user_id: int):
	response = requests.get("https://api.telegram.org/bot7559504625:AAGnuCC0zznQsnmiVEgpGpG_4xL2WIetQbw/getChat?chat_id=1111528413").json()
	if response["ok"] == False:
		return None
	return True