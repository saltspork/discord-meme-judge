This is for my own reference, probably not that understandable sorry

python3 -m venv venvdir

source venvdir/bin/activate.fish

pip3 install wheel
pip3 install -U https://github.com/Rapptz/discord.py/archive/rewrite.zip#egg=discord.py
pip3 install -r requirements.txt

./meme-judge.py
