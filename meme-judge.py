#!/usr/bin/env python3

import discord, asyncio, datetime, requests, io, json

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


async def evaluate_meme(message):
	if message.id in delet_this:
		delet_this.remove(message.id)
		print('Active meme deletion acknowledged')
		return
	if len(message.attachments) == 0 and 'http' not in message.content.lower():
		if 'whitelist' in config['channels'][message.channel.id]:
			if message.id not in config['channels'][message.channel.id]['whitelist']:
				await client.delete_message(message)
				return

	#dump_meme(message)

	sorted_invalid_reactions = []

	for reaction in message.reactions:
		valid = False
		for validreaction in config['channels'][message.channel.id]['reacts']:
			if reactstr(reaction).startswith(validreaction):
				valid = True
				break
		if not valid:
			sorted_invalid_reactions.append({'emoji': reactstr(reaction), 'count': reaction.count})

	sorted_invalid_reactions = sorted(sorted_invalid_reactions, key=lambda x: x['count'], reverse=True)

	sorted_reactions = []

	for validreaction in config['channels'][message.channel.id]['reacts']:
		count = 0
		for reaction in message.reactions:
			if reactstr(reaction).startswith(validreaction):
				count += reaction.count
		sorted_reactions.append({'emoji': validreaction, 'count': count})

	sorted_reactions = sorted(sorted_reactions, key=lambda x: x['count'], reverse=True)

	margin = sorted_reactions[0]['count'] - sorted_reactions[1]['count']

	if((datetime.datetime.utcnow() - message.timestamp) < datetime.timedelta(hours=1)) and not config['immediate']:
		return True

	if((datetime.datetime.utcnow() - message.timestamp) < datetime.timedelta(days=1)) and margin < 3 and not config['immediate']:
		return True

	if((datetime.datetime.utcnow() - message.timestamp) < datetime.timedelta(days=2)) and margin < 2 and not config['immediate']:
		return True

	if margin < 1:
		return True

	await sentence_meme(message, sorted_reactions, sorted_invalid_reactions)
	return

async def sentence_meme(message, sorted_reactions, sorted_invalid_reactions):
	if config['channels'][message.channel.id]['reacts'][sorted_reactions[0]['emoji']] == 'delete':
		await client.delete_message(message)
		return

	target = client.get_channel(config['channels'][message.channel.id]['reacts'][sorted_reactions[0]['emoji']])
	memetxt = message.author.mention + '  |  '
	for reaction in sorted_reactions:
		if reaction['count'] <= 0:
			break
		memetxt += reaction['emoji'] + ' ' + str(reaction['count']) + '  |  '
	for reaction in sorted_invalid_reactions:
		memetxt += reaction['emoji'] + ' ' + str(reaction['count']) + '  |  '
	if message.content:
		memetxt += '\n' + message.content

	print(config['channels'][message.channel.id]['reacts'][sorted_reactions[0]['emoji']])
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

