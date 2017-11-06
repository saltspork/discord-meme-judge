#!/usr/bin/env python3

import discord, asyncio, datetime, requests, io, json, collections

with open('config.json') as f:
	config = json.load(f)

under_deliberation = []
delet_this = []

client = discord.Client()

@client.event
async def on_ready():
	print('Logged in as')
	print(client.user.name)
	print(client.user.id)
	print('Invite: ' + discord.utils.oauth_url(client.user.id))
	print('------\n')

	while True:
		for channel in config['channels']:
			async for log in client.logs_from(client.get_channel(channel), limit=1000):
				if log.id not in under_deliberation:
					await evaluate_meme(log)
		await asyncio.sleep(600)

def reactstr(reaction):
	if reaction.custom_emoji:
		return '<:' + reaction.emoji.name + ':' + reaction.emoji.id + '>'
	elif type(reaction.emoji) is str:
		return reaction.emoji

def dump_meme(message):
	print('------')
	print('Age: ' + str(datetime.datetime.utcnow() - message.timestamp))
	print('Content: ' + message.content)
	print('CID: ' + message.channel.id)
	print('SID: ' + message.channel.server.id)
	for attachment in message.attachments:
		for attr in message.attachments[0]:
			print(attr + ' ' + str(message.attachments[0][attr]))
	for reaction in message.reactions:
		print('React: ' + reactstr(reaction) + ' x' + str(reaction.count))

	print('------\n')


def matchreact(react, valids):
	for valid in valids:
		if react.startswith(valid):
				return True, valid
	return False, react

async def evaluate_meme(message):
	if message.id in delet_this:
		delet_this.remove(message.id)
		print('Active meme deletion acknowledged')
		return

	if 'whitelist' in config['channels'][message.channel.id]:
		if message.id in config['channels'][message.channel.id]['whitelist']:
			return

	if len(message.attachments) == 0 and 'http' not in message.content.lower():
		await client.delete_message(message)
		return

	users = {}
	valid_mess = []
	invalid_mess = []

	for reaction in message.reactions:
		for user in await client.get_reaction_users(reaction):
			if user in users:
				users[user].append(reactstr(reaction))
			else:
				users[user] = [reactstr(reaction)]

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
	

	if((datetime.datetime.utcnow() - message.timestamp) < datetime.timedelta(hours=1)) and not config['immediate']:
		return True

	if((datetime.datetime.utcnow() - message.timestamp) < datetime.timedelta(days=1)) and margin < 3 and not config['immediate']:
		return True

	if((datetime.datetime.utcnow() - message.timestamp) < datetime.timedelta(days=2)) and margin < 2 and not config['immediate']:
		return True

	if margin < 1:
		return True

	await sentence_meme(message, valid_grouped + invalid_grouped)
	return

async def sentence_meme(message, reacts):
	if config['channels'][message.channel.id]['reacts'][reacts[0][0]] == 'delete':
		await client.delete_message(message)
		return

	target = client.get_channel(config['channels'][message.channel.id]['reacts'][reacts[0][0]])
	memetxt = message.author.mention + '  |  '
	for reaction in reacts:
		memetxt += reaction[0] + ' ' + str(reaction[1]) + '  |  '
	if message.content:
		memetxt += '\n' + message.content

	print(config['channels'][message.channel.id]['reacts'][reacts[0][0]])
	print(memetxt)

	if len(message.attachments) > 0:
		print(message.attachments[0]['url'])
		r = requests.get(message.attachments[0]['url'])
		attachment = io.BytesIO(r.content)
		await client.send_file(target, attachment, filename=message.attachments[0]['filename'] ,content=memetxt)
	else:
		await client.send_message(target, memetxt)

	await client.delete_message(message)

@client.event
async def on_message(message):
	if message.channel.id in config['channels'] and message.id not in under_deliberation:
		under_deliberation.append(message.id)
		while await evaluate_meme(message):
			print('Meme active')
			await client.wait_for_reaction(None, message=message, timeout=300)
		under_deliberation.remove(message.id)
		print('Meme becoming inactive')
	dump_meme(message)


@client.event
async def on_message_delete(message):
	if message.id in under_deliberation:
		delet_this.append(message.id)
		print('Active meme deleted')
		dump_meme(message)

@client.event
async def on_reaction_add(reaction, user):
	print('Global react event: ' + reactstr(reaction))
	dump_meme(reaction.message)

client.run(config['token'])

