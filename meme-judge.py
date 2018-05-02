#!/usr/bin/env python3

import discord, asyncio, aiohttp, datetime, io, json, collections, math, datetime

with open('config.json') as f:
	config = json.load(f, object_pairs_hook=collections.OrderedDict)

nospam = []
for channel in config['channels']:
	nospam.extend(list(config['channels'][channel]['reacts'].values()))

processing = []

client = discord.Client()

@client.event
async def on_ready():
	print('Logged in as')
	print(client.user.name)
	print(client.user.id)
	print('Invite: ' + discord.utils.oauth_url(client.user.id))
	print('------\n')

@client.event
async def on_message(message):
	await evaluate_meme(message)

@client.event
async def on_reaction_add(reaction, user):
	await evaluate_meme(reaction.message)

async def refresh_memes():
	await client.wait_until_ready()
	while not client.is_closed:
		logtime('global refresh starting')
		for channel in config['channels']:
			async for logmsg in client.logs_from(client.get_channel(channel)):
				await evaluate_meme(logmsg)
		logtime('global refresh finished, sleeping for '+str(config['refresh_interval']))
		await asyncio.sleep(config['refresh_interval'])
	logtime('global refresh loop exited, this is probably bad')

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
		logtime(message.id+' race averted')
		return
	else:
		processing.append(message.id)
		logtime(message.id+' evaluation starting')
		await unsafe_evaluate_meme(message)
		logtime(message.id+' evaluation finished')
		processing.remove(message.id)

async def unsafe_evaluate_meme(message):
	if message.author.id == client.user.id:
		return
	
	if message.channel.id in nospam:
		logtime(message.id+' editing possible')
		if message.content.startswith("<@"+client.user.id+"> "):
			tokens=message.content.split(' ', 2)
			editme = await client.get_message(message.channel, tokens[1])
			if editme.author.id == client.user.id:
				await client.edit_message(editme, editme.content + '\n' + tokens[2] + ' (' + message.author.mention + ')')
				logtime(message.id+' editing edited')
		await client.delete_message(message)
		logtime(message.id+' editing deleted')
		return
	
	if message.channel.id not in config['channels']:
		return

	if 'whitelist' in config['channels'][message.channel.id]:
		if message.id in config['channels'][message.channel.id]['whitelist']:
			return

	if len(message.attachments) == 0 and 'http' not in message.content.lower():
		logtime(message.id+' invalid deleting')
		await client.delete_message(message)
		logtime(message.id+' invalid deleted')
		return

	users = {client.user.id:[]}
	valid_mess = []
	invalid_mess = []

	logtime(message.id+' valid enumerating')

	for reaction in message.reactions:
		for user in await client.get_reaction_users(reaction):
			if user.id in users:
				users[user.id].append(str(reaction.emoji))
			else:
				users[user.id] = [str(reaction.emoji)]

	logtime(message.id+' valid enumerated')

	if len(message.attachments) >= 0 and message.attachments[0]['size'] >= config['max_size'] and str(config['alert']) not in users[client.user.id]:
		logtime(message.id+' oversize placeholding')
		await client.add_reaction(message, config['alert'])
		logtime(message.id+' oversize placeholded')

	for reaction in config['channels'][message.channel.id]['reacts']:
		if reaction.startswith('<:'):
			reactwith = lookup_emoji(reaction, message.server)
		else:
			reactwith = reaction
		if str(reactwith) not in users[client.user.id] and reactwith != False:
				logtime(message.id+' valid placeholding '+str(reactwith))
				await client.add_reaction(message, reactwith)
				logtime(message.id+' valid placeholded '+str(reactwith))

	del users[client.user.id]

	for user in users:
		valid_counted = []
		invalid_counted = []

		for react in users[user]:
			valid, subreact = matchreact(react, config['channels'][message.channel.id]['reacts'])
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

	if config['channels'][message.channel.id]['reacts'][valid_grouped[0][0]] == 'delete' and margin < 2:
		return True

	# after target seconds, only a margin of 1 is required
	elapsed = (datetime.datetime.utcnow() - message.timestamp).total_seconds()

	if margin < math.ceil(1-math.log(elapsed/config['channels'][message.channel.id]['target'], 2)) and not config['immediate']:
		return True

	return await sentence_meme(message, valid_grouped + invalid_grouped)


async def sentence_meme(message, reacts):
	logtime(message.id+' valid voted')
	if config['channels'][message.channel.id]['reacts'][reacts[0][0]] == 'delete':
		await client.delete_message(message)
		logtime(message.id+' valid deleted')
		return
	elif config['channels'][message.channel.id]['reacts'][reacts[0][0]] == 'stalemate':
		return True

	target = client.get_channel(config['channels'][message.channel.id]['reacts'][reacts[0][0]])
	memetxt = message.author.mention + '  |  '
	for reaction in reacts:
		reactwith = reaction[0]
		if reactwith.startswith('<:') and not reactwith.endswith('>'):
			reactwith = str(lookup_emoji(reactwith, message.server))
		memetxt += reactwith + ' ' + str(reaction[1]) + '  |  '
	if message.content:
		memetxt += '\n' + message.content

	if len(message.attachments) > 0:
		logtime(message.id+' valid attachment downloading')
		async with aiohttp.ClientSession() as session:
			async with session.get(message.attachments[0]['url']) as response:
				attached_bytes = await response.read()
				attachment = io.BytesIO(attached_bytes)
		logtime(message.id+' valid attachment uploading')
		await client.send_file(target, attachment, filename=message.attachments[0]['filename'] ,content=memetxt)
		logtime(message.id+' valid attachment uploaded')
	else:
		logtime(message.id+' valid textonly posting')
		await client.send_message(target, memetxt)
		logtime(message.id+' valid textonly posted')

	await client.delete_message(message)
	logtime(message.id+' valid original deleted')

def logtime(message):
	print(str(datetime.datetime.now())+' '+message)


client.loop.create_task(refresh_memes())
client.run(config['token'])
