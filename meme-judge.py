#!/usr/bin/env python3

import discord, asyncio, datetime, requests, io, json, collections, math

with open('config.json') as f:
	config = json.load(f, object_pairs_hook=collections.OrderedDict)

nospam = []
for channel in config['channels']:
	nospam.extend(list(config['channels'][channel]['reacts'].values()))

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

def lookup_emoji(prefix, server):
	for emoji in server.emojis:
		if str(emoji).startswith(prefix):
			return emoji
	return False

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
		print('React: ' + str(reaction.emoji) + ' x' + str(reaction.count))

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

	users = {client.user.id:[]}
	valid_mess = []
	invalid_mess = []

	for reaction in message.reactions:
		for user in await client.get_reaction_users(reaction):
			if user.id in users:
				users[user.id].append(str(reaction.emoji))
			else:
				users[user.id] = [str(reaction.emoji)]


	for reaction in config['channels'][message.channel.id]['reacts']:
		if reaction not in users[client.user.id]:
			reactwith = reaction
			if reactwith.startswith('<:'):
				reactwith = lookup_emoji(reaction, message.server)
			if reactwith != False:
				await client.add_reaction(message, reactwith)

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

	# after target seconds, only a margin of 1 is required
	elapsed = (datetime.datetime.utcnow() - message.timestamp).total_seconds()

	if margin < math.ceil(1-math.log(elapsed/config['channels'][message.channel.id]['target'], 2)) and not config['immediate']:
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
		reactwith = reaction[0]
		if reactwith.startswith('<:') and not reactwith.endswith('>'):
			reactwith = str(lookup_emoji(reactwith, message.server))
		memetxt += reactwith + ' ' + str(reaction[1]) + '  |  '
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
	dump_meme(message)
	if message.author.id == client.user.id:
		return
	elif message.channel.id in config['channels'] and message.id not in under_deliberation:
		under_deliberation.append(message.id)
		while await evaluate_meme(message):
			#print('Meme active')
			await client.wait_for_reaction(None, message=message, timeout=300)
		under_deliberation.remove(message.id)
		print('Meme becoming inactive')
	elif message.content.startswith("<@"+client.user.id+"> "):
		tokens=message.content.split(' ', 2)
		editme = await client.get_message(message.channel, tokens[1])
		if editme.author.id == client.user.id:
			await client.edit_message(editme, editme.content + '\n' + tokens[2])
			await client.delete_message(message)
	elif message.channel.id in nospam:
			await client.delete_message(message)


@client.event
async def on_message_delete(message):
	if message.id in under_deliberation:
		delet_this.append(message.id)
		print('Active meme deleted')
		dump_meme(message)

@client.event
async def on_reaction_add(reaction, user):
	print('Global react event: ' + str(reaction.emoji))
	dump_meme(reaction.message)

client.run(config['token'])

