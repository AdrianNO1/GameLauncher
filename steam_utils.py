import json
import win32ui
import win32gui
import win32con
import win32api
import os
import requests
from PIL import Image
from difflib import SequenceMatcher
from pathlib import Path

CACHE_FILE = "steam_id_cache.json"

def load_cache():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading cache: {str(e)}")
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=4)
    except Exception as e:
        print(f"Error saving cache: {str(e)}")

def similar(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def find_steam_id(game_name):
    cache = load_cache()
    
    if game_name in cache:
        return cache[game_name]
        
    try:
        url = f"https://steamcommunity.com/actions/SearchApps/{game_name}"
        response = requests.get(url)
        
        if response.status_code == 200:
            results = response.json()
            
            if results:
                best_match = max(results, key=lambda x: similar(x["name"], game_name))
                similarity = similar(best_match["name"], game_name)
                print(f"Similarity for {game_name}: {similarity}")
                
                if similarity > 0.6 or True:
                    cache[game_name] = best_match["appid"]
                    save_cache(cache)
                    return best_match["appid"]
                
        cache[game_name] = None
        save_cache(cache)
        return None
    except Exception as e:
        print(f"Error finding Steam ID for {game_name}: {str(e)}")
        cache[game_name] = None
        save_cache(cache)
        return None

def download_image(url, save_path):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(response.content)
            return True
    except Exception as e:
        print(f"Error downloading image: {str(e)}")
    return False

def get_file_icon(file_path, size=32):
    try:
        _, ext = os.path.splitext(file_path)
        
        large, small = win32gui.ExtractIconEx(file_path, 0)
        if large:
            win32gui.DestroyIcon(large[0])
        if small:
            win32gui.DestroyIcon(small[0])
        
        ico_x = win32api.GetSystemMetrics(win32con.SM_CXICON)
        ico_y = win32api.GetSystemMetrics(win32con.SM_CYICON)
        
        large_flag = win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
        
        hicon = win32gui.ExtractIcon(
            0,
            file_path,
            0)
        
        if hicon == 0:
            shell32_file = os.path.join(os.environ["SystemRoot"], "System32", "shell32.dll")
            file_info = win32gui.GetFileAttributes(file_path)
            
            if file_info & win32con.FILE_ATTRIBUTE_DIRECTORY:
                hicon = win32gui.ExtractIcon(0, shell32_file, 3)
            else:
                hicon = win32gui.ExtractIcon(0, shell32_file, 0)
        
        hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
        hbmp = win32ui.CreateBitmap()
        hbmp.CreateCompatibleBitmap(hdc, size, size)
        hdc = hdc.CreateCompatibleDC()
        
        hdc.SelectObject(hbmp)
        hdc.DrawIcon((0, 0), hicon)
        
        bmpstr = hbmp.GetBitmapBits(True)
        img = Image.frombuffer(
            "RGBA",
            (size, size),
            bmpstr,
            "raw",
            "BGRA",
            0,
            1
        )

        if img.getbbox() is None:
            return None

        img_path = Path("game_images") / f"{os.path.basename(file_path)}_icon.png"
        img.save(img_path)

        return str(img_path)
        
    except Exception as e:
        print(f"Error extracting icon: {str(e)}")
        return None

def update_game_data():
    with open("games.json", "r") as f:
        data = json.load(f)
    
    images_dir = Path("game_images")
    images_dir.mkdir(exist_ok=True)
    
    modified = False
    
    for game in data["games"]:
        if game.get("no_steam") or game.get("deleted", False):
            continue

        if not game.get("exe_path"):
            print(f"{game['name']} has no exe path")
            
        if not game.get("steam_id"):
            steam_id = find_steam_id(game["name"])
            if steam_id:
                game["steam_id"] = str(steam_id)
                modified = True
                print(f"Found Steam ID for {game['name']}: {steam_id}")
            else:
                print("found no steam id :(")
        
        if not game.get("image_path") or not os.path.exists(game.get("image_path", "")):
            if game.get("steam_id"):
                image_filename = f"{game['steam_id']}_capsule.jpg"
                image_path = images_dir / image_filename
                primary_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{game['steam_id']}/capsule_616x353.jpg"
                
                if not download_image(primary_url, image_path):
                    image_filename = f"{game['steam_id']}_header.jpg"
                    image_path = images_dir / image_filename
                    fallback_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{game['steam_id']}/header.jpg"
                    
                    if download_image(fallback_url, image_path):
                        game["image_path"] = str(image_path)
                        modified = True
                        print(f"Downloaded fallback image for {game['name']}")
                else:
                    game["image_path"] = str(image_path)
                    modified = True
                    print(f"Downloaded primary image for {game['name']}")

        if not game.get("icon_path") or not os.path.exists(game.get("icon_path", "")):
            icon = get_file_icon(game.get("exe_path"))
            if icon:
                game["icon_path"] = icon
                modified = True
                print(f"Extracted icon for {game['name']}")
            else:
                if game.get("image_path"):
                    print(f"Could not extract icon for {game['name']}. Using header image instead")
                    game["icon_path"] = game["image_path"]
                    modified = True
                else:
                    print(f"Could not extract icon for {game['name']} and no header image found")
    
    if modified:
        with open("games.json", "w") as f:
            json.dump(data, f, indent=4)
        print("Games data updated successfully")

if __name__ == "__main__":
    update_game_data()
