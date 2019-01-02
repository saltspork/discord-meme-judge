#!/usr/bin/env python3

import discord, asyncio, aiohttp, datetime, io, json, collections, math, datetime, traceback

with open('config.json') as f:
	config = json.load(f, object_pairs_hook=collections.OrderedDict)

# Channels that memes are sorted into, in which only messages requesting edits are allowed
nospam = []
for channel in config['channels']:
	nospam.extend(list(config['channels'][channel]['reacts'].values()))

processing = []


class MyClient(discord.Client):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		# create the background task and run it in the background
		self.bg_task = self.loop.create_task(self.refresh_memes())

	async def on_ready(self):
		print('Logged in as')
		print(self.user.name)
		print(self.user.id)
		print('------')

	async def refresh_memes(self):
		logtime('main refresh loop entered')
		await self.wait_until_ready()
		logtime('main refresh loop ready')
		while True:
			if not self.is_closed():
				logtime('global refresh starting')
				for channel in config['channels']:
					async for logmsg in self.get_channel(int(channel)).history():
						await evaluate_meme(logmsg)
				logtime('global refresh finished, sleeping for '+str(config['refresh_interval']))
			else:
				logtime('global refresh skipped, connection not open')
			await asyncio.sleep(config['refresh_interval'])
		logtime('main refresh loop exited')

client = MyClient()

@client.event
async def on_message(message):
	await evaluate_meme(message)

@client.event
async def on_reaction_add(reaction, user):
	await evaluate_meme(reaction.message)


def lookup_emoji(prefix, server):
	for emoji in server.emojis:
		if str(emoji).startswith(prefix):
			return emoji
	return False

def matchreact(react, valids):
	for valid in valids:
		if react.startswith(valid):
				if valids[valid] == 'suggest':
					return False, valid
				else:
					return True, valid
	return False, react

# lazy wrapper to avoid races
async def evaluate_meme(message):
	if message.id in processing:
		logtime(str(message.id)+' race averted')
		return
	else:
		processing.append(message.id)
		logtime(str(message.id)+' evaluation starting')
		try:
			await unsafe_evaluate_meme(message)
		except Exception as e:
			print("PYTHON ERROR: " + str(e))
			print(traceback.format_exc())
		logtime(str(message.id)+' evaluation finished')
		processing.remove(message.id)

async def unsafe_evaluate_meme(message):
	if message.author.id == client.user.id:
		return
	
	if message.channel.id in nospam:
		logtime(str(message.id)+' editing possible')
		if message.content.startswith("<@"+str(client.user.id)+"> "):
			tokens=message.content.split(' ', 2)
			editme = await message.channel.get_message(tokens[1])
			if editme.author.id == client.user.id:
				await editme.edit(content=editme.content + '\n' + tokens[2] + ' (' + message.author.mention + ')')
				logtime(str(message.id)+' editing edited')
		await message.delete()
		logtime(str(message.id)+' editing deleted')
		return
	
	if str(message.channel.id) not in config['channels']:
		return

	if 'whitelist' in config['channels'][str(message.channel.id)]:
		if message.id in config['channels'][str(message.channel.id)]['whitelist']:
			return

	if len(message.attachments) == 0 and 'http' not in message.content.lower():
		logtime(str(message.id)+' invalid deleting')
		await message.delete()
		logtime(str(message.id)+' invalid deleted')
		return

	users = {client.user.id:[]}
	valid_mess = []
	invalid_mess = []

	logtime(str(message.id)+' valid enumerating')

	for reaction in message.reactions:
		async for user in reaction.users():
			if user.id in users:
				users[user.id].append(str(reaction.emoji))
			else:
				users[user.id] = [str(reaction.emoji)]

	logtime(str(message.id)+' valid enumerated')

	if len(message.attachments) > 0 and message.attachments[0].size >= config['max_size']:
		warntxt = message.author.mention + ' your meme ' + message.attachments[0].filename + ' is larger than ' + str(config['max_size']/1000) + ' KB.\nPlease compress it more until bots get Nitro.'
		await client.get_channel(config['channels'][str(message.channel.id)]['infochan']).send(warntxt)
		await message.delete()
		return

	for reaction in config['channels'][str(message.channel.id)]['reacts']:
		if reaction.startswith('<:'):
			reactwith = lookup_emoji(reaction, message.guild)
		else:
			reactwith = reaction
		if str(reactwith) not in users[client.user.id] and reactwith != False:
				logtime(str(message.id)+' valid placeholding '+str(reactwith))
				await message.add_reaction(reactwith)
				logtime(str(message.id)+' valid placeholded '+str(reactwith))

	del users[client.user.id]

	for user in users:
		valid_counted = []
		invalid_counted = []

		for react in users[user]:
			valid, subreact = matchreact(react, config['channels'][str(message.channel.id)]['reacts'])
			if not valid:
				invalid_counted.append(subreact)
			elif subreact not in valid_counted:
				valid_counted.append(subreact)

		valid_mess += valid_counted
		invalid_mess += invalid_counted

	valid_grouped = collections.Counter(valid_mess).most_common()
	invalid_grouped = collections.Counter(invalid_mess).most_common()

	if len(valid_grouped) < 1:
		return True
	elif len(valid_grouped) == 1:
		margin = valid_grouped[0][1]
	else:
		margin = valid_grouped[0][1] - valid_grouped[1][1]

	if margin < 1:
		return True

	if config['channels'][str(message.channel.id)]['reacts'][valid_grouped[0][0]] == 'delete' and margin < 2:
		return True

	# after target seconds, only a margin of 1 is required
	elapsed = (datetime.datetime.utcnow() - message.created_at).total_seconds()

	if margin < math.ceil(1-math.log(elapsed/config['channels'][str(message.channel.id)]['target'], 2)) and not config['immediate']:
		return True

	return await sentence_meme(message, valid_grouped + invalid_grouped)


async def sentence_meme(message, reacts):
	logtime(str(message.id)+' valid voted')
	if config['channels'][str(message.channel.id)]['reacts'][reacts[0][0]] == 'delete':
		await message.delete()
		logtime(str(message.id)+' valid deleted')
		return
	elif config['channels'][str(message.channel.id)]['reacts'][reacts[0][0]] == 'stalemate':
		return True

	target = client.get_channel(config['channels'][str(message.channel.id)]['reacts'][reacts[0][0]])
	memetxt = message.author.mention + '  |  '
	for reaction in reacts:
		reactwith = reaction[0]
		if reactwith.startswith('<:') and not reactwith.endswith('>'):
			reactwith = str(lookup_emoji(reactwith, message.guild))
		memetxt += reactwith + ' ' + str(reaction[1]) + '  |  '
	if message.content:
		memetxt += '\n' + message.content

	if len(message.attachments) > 0:
		logtime(str(message.id)+' valid attachment downloading')
		async with aiohttp.ClientSession() as session:
			async with session.get(message.attachments[0].url) as response:
				attached_bytes = await response.read()
				attachment = io.BytesIO(attached_bytes)
		logtime(str(message.id)+' valid attachment uploading')
		await target.send(memetxt, file=discord.File(attachment, message.attachments[0].filename))
		logtime(str(message.id)+' valid attachment uploaded')
	else:
		logtime(str(message.id)+' valid textonly posting')
		await target.send(memetxt)
		logtime(str(message.id)+' valid textonly posted')

	await message.delete()
	logtime(str(message.id)+' valid original deleted')

def logtime(message):
	print(str(datetime.datetime.now())+' '+message)


client.run(config['token'])


