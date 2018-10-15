# -*- coding: utf-8 -*-

import re									#  For find-replace regular expressions
import sys									#  For overwriting output to the screen (verbose mode)
import requests								#  Part of BeautifulSoup
import bs4									#  Used to find() the censored bits
from bs4 import BeautifulSoup
from guess_language import *				#  Pretty lame trigram detector... but it's free
import MySQLdb								#  Used for DB operations
import datetime								#  Used for time stamping our retrievals
from datetime import datetime				#  Used for time stamping our retrievals
import time									#  Track how long things take

#  The job of this class is to periodically grab a bunch of posts from FreeWeibo.com,
#  parse them and save them to the database. Another routine will perform analysis, which takes
#  a bit more time. The idea here is to constantly be retrieving as much content as possible.
class FreeWeiboFetcher:
	#  fetcher = FreeWeiboFetcher('localhost', 'censor', 'blockme', 'corpora')
	def __init__(self, dbHost=None, dbUser=None, dbPword=None, dbTable=None):
		self.posts = []						#  List of FreeWeibo posts, stored here as dictionary objects:
											#  One {} per post:
											#  ['content'] = DB-safe HTML of post
											#  ['data-id'] = identifier in FreeWeibo
											#  ['weibo-id'] = identifier in Weibo
											#  ['pub-date'] = Date time of publication
											#  ['date-retrieved'] = The date we collected this post
		self.topics = []					#  List of top ten "hot topics", taken from the FreeWeibo
											#  right-hand side-bar. One tuple per topic:
											#  (Link text, Link)

		self.link = None					#  MySQL link
		self.dbHost = dbHost				#  String indicating database host
		self.dbUser = dbUser				#  String indicating database host
		self.dbPword = dbPword				#  String indicating database host
		self.dbTable = dbTable				#  String indicating database host

		self.removeLB = True				#  Whether we remove line breaks
		self.replaceSpecial = True			#  Whether to use the replacement dictionary to swap out special chars
		self.replaceDict = self.initReplace()
		self.verbose = False				#  Whether to print progress to screen (sometimes spits up funky chars)
		self.debugFile = False				#  Whether to output queries to a debug file

		self.startTime = None				#  Time this routine
		self.stopTime = None

		return

	#  The way FreeWeibo works, this routine just scrapes whatever's on the page.
	#  They do not appear to archive censored posts--at least not conveniently for retrieval.
	def fetch(self):
		url = "https://freeweibo.com/"
		page = requests.get(url)
		if page.status_code == 200:

			self.startTimer()				#  Begin timing the scrape

			html = page.text
			#  Chuck it into the soup
			soup = BeautifulSoup(html, 'html.parser')
			#  Get all censored posts
			censored = soup.findAll('div', attrs={'class':'censored-1'})
			if self.verbose:
				print("Scraped " + str(len(censored)) + " censored posts from FreeWeibo.")
			#  Prepare date matching pattern:
			#  <a href="/weibo/4209800710047255" target="/weibo/420">2018年02月21日 09:56</a>
			regex = r'<a href="/weibo/(\d+)" target=".+">(\d+)\xe5\xb9\xb4(\d+)\xe6\x9c\x88(\d+)\xe6\x97\xa5 (\d+):(\d+)</a>'
			for post in censored:
				dataId = post['data-id']	#  FreeWeibo post unique identifier
											#  Only one content div per post:
											#  Convert it to a string and cut away the enclosing tags.
											#  This slice-notation is cheesey but straightforward.
				content  = str(post.find('div', attrs={'class':'content'}))[21:-6]
				lang, langConfidence = self.determineLanguage(content)

				#  Remove line breaks AFTER we've attempted to identify the language
				if self.removeLB:
					if content is not None:
						content = ' '.join(content.splitlines())

				#  Find-and-replace web-formatted characters
				if self.replaceSpecial:
					for k, v in self.replaceDict.items():
						if content is not None:
							content = re.sub(k, v, content)

					#  &#nnn;  means the number is DECIMAL     convert to \ummm where mmm is hex for nnn
					#  &#xnnn; means the number is HEXADECIMAL convert to \unnn
					if content is not None:
						content = unicode(content, "utf-8")
						content = re.sub(r'&#(\d+);', lambda m: r'\u' + "{0:#0{1}x}".format(int(m.group()[2:-1]), 6)[2:], content)
						content = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: r'\u' + "{0:#0{1}x}".format(int(m.group(1), 16), 6)[2:], content)

											#  Lot of information in this line:
											#  An original Weibo ID		(\1)
											#  The year					(\2)
											#  The month				(\3)
											#  The day					(\4)
											#  The hour					(\5)
											#  The minute				(\6)
				postDate = str(post.find('div', attrs={'class':'date'}).find('a'))
				matches = re.findall(regex, postDate)
				weiboId = matches[0][0]
				weiboPubYear = int(matches[0][1])
				weiboPubMonth = int(matches[0][2])
				weiboPubDay = int(matches[0][3])
				weiboPubHour = int(matches[0][4])
				weiboPubMinute = int(matches[0][5])

				if self.verbose:
					noticeStr  = "\tPublished "
					noticeStr += str(weiboPubMonth) + '.' + str(weiboPubDay) + '.' + str(weiboPubYear) + ' '
					noticeStr += lang + ', ' + str(langConfidence)
					print(noticeStr)

				self.posts.append( {} )		#  Append new post
				safe = repr(content)[2:-1]	#  Add post text (render for DB storage)
				safe = re.sub(r'\"', '\\\"', safe)
				safe = re.sub(r'\u', '\\u', safe)
				self.posts[-1]['content'] = safe
				self.posts[-1]['hash'] = hash(doc['content']) % ((sys.maxsize + 1) * 2)
											#  Add post data
				self.posts[-1]['data-id'] = dataId
				self.posts[-1]['weibo-id'] = weiboId
				self.posts[-1]['pub-date'] = datetime(weiboPubYear, weiboPubMonth, weiboPubDay, \
				                                      weiboPubHour, weiboPubMinute)
				self.posts[-1]['date-retrieved'] = datetime.now()

				#  21FEB18: The markup is confusing the language-detector, so we're just going
				#  to TELL Python, "This is Chinese. Trust me. I'm CONFIDENT!"

				#self.posts[-1]['lang-detected'] = lang
				#self.posts[-1]['confidence'] = langConfidence
				self.posts[-1]['lang-detected'] = 'zh'
				self.posts[-1]['confidence'] = 1.0

			#  Get all hot topics
			sidebar = soup.find('div', attrs={'id':'right'})
			ol = sidebar.find('ol')

			if self.verbose:
				print("FreeWeibo hot topics:")

			#  Prepare topic matching pattern:
			#  <li><a href="/weibo/%E8%96%84%E7%86%99%E6%9D%A5">薄熙来</a></li>
			regex = r'<li><a href="/(weibo/[^\"]+)">(.+)</a></li>'
			lis = ol.findAll('li')
			for li in lis:

				content = str(li)

				#  Remove line breaks
				if self.removeLB:
					if content is not None:
						content = ' '.join(content.splitlines())

				#  Find-and-replace web-formatted characters
				if self.replaceSpecial:
					for k, v in self.replaceDict.items():
						if content is not None:
							content = re.sub(k, v, content)

					#  &#nnn;  means the number is DECIMAL     convert to \ummm where mmm is hex for nnn
					#  &#xnnn; means the number is HEXADECIMAL convert to \unnn
					if content is not None:
						content = unicode(content, "utf-8")
						content = re.sub(r'&#(\d+);', lambda m: r'\u' + "{0:#0{1}x}".format(int(m.group()[2:-1]), 6)[2:], content)
						content = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: r'\u' + "{0:#0{1}x}".format(int(m.group(1), 16), 6)[2:], content)

				matches = re.findall(regex, content)
				topicLink = matches[0][0]
				topicText = matches[0][1]

				safe = repr(topicText)[2:-1]#  Render topic text for DB storage
				safe = re.sub(r'\"', '\\\"', safe)
				safe = re.sub(r'\u', '\\u', safe)
				self.topics.append( (safe, topicLink) )

				if self.verbose:
					print("\t" + topicText)

		elif self.verbose:
			print('Page connection error.')
		return

	#  Save the internal list of dictionary objects to the database, checking each time that
	#  we do not already have this one. The CONTENT field and the PUB-DATE constitute a unique identifier.
	#  Return the number of UNIQUE records added
	def save(self):
		if self.link is not None:			#  Attempt to save to the DB

			if self.debugFile:
				fh = open('freeweibo-' + str(time.time()) + '.debug', 'w')

			totalRecords = len(self.posts)
			recordsWritten = 0				#  Track progress

			if self.verbose:
				print("\n" + str(totalRecords) + " posts scraped (not all may be unique)\n")
				sys.stdout.write('Writing to database: 0%' + "\r")
				sys.stdout.flush()

			cursor = self.link.cursor(MySQLdb.cursors.DictCursor)
			for post in self.posts:

				foundUnique = False			#  Find out whether we have this post already

				if post['hash'] is not None and post['pub-date'] is not None:
					query  = 'SELECT * FROM freeweibo'
					query += ' WHERE hash = ' + str(post['hash'])
					query += ' AND pub_date = "' + post['pub-date'].strftime('%Y-%m-%d %H:%M:%S') + '";'
					cursor.execute(query)
					result = cursor.fetchall()
					if len(result) == 0:
						foundUnique = True

				if foundUnique:				#  Add record to the database (accounting for its being potentially partial)
					query = 'INSERT INTO freeweibo('
					vals = ''

					#  HASH is an unsigned long int
					if post['hash'] is not None:
						query += 'hash, '
						#vals += u'"' + post['content'].encode('utf-8').decode('unicode-escape') + u'", '
						vals += str(post['hash']) + ', '
					#  CONTENT is UNICODE
					if post['content'] is not None:
						query += 'content, '
						#vals += u'"' + post['content'].encode('utf-8').decode('unicode-escape') + u'", '
						vals += '"' + post['content'] + '", '
					#  DATA-ID is ASCII
					if post['data-id'] is not None:
						query += 'data_id, '
						vals += '"' + post['data-id'] + '", '
					#  WEIBO-ID is ASCII
					if post['weibo-id'] is not None:
						query += 'weibo_id, '
						vals += '"' + post['weibo-id'] + '", '
					#  PUBLICATION-DATE is ASCII
					if post['pub-date'] is not None:
						query += 'pub_date, '
						vals += '"' + post['pub-date'].strftime('%Y-%m-%d %H:%M:%S') + '", '
					#  DATE-RETRIEVED is ASCII
					if post['date-retrieved'] is not None:
						query += 'ret_date, '
						vals += '"' + post['date-retrieved'].strftime('%Y-%m-%d %H:%M:%S') + '", '
					#  LANGUAGE-DETECTED is ASCII
					if post['lang-detected'] is not None:
						query += 'lang_detected, '
						vals += '"' + post['lang-detected'] + '", '
					#  CONFIDENCE is float
					if post['confidence'] is not None:
						query += 'confidence'
						vals += str(post['confidence'])

					query += ') VALUES(' + vals + ');'

					if self.debugFile:
						fh.write(query + "\n")

					cursor.execute(query)
					self.link.commit()

					recordsWritten += 1

					if self.verbose:
						sys.stdout.write('Writing to database: ' + \
					                     str(int(float(recordsWritten) / float(totalRecords) * 100)) + '%' + "\r")
						sys.stdout.flush()
				else:						#  Record NOT unique, but affects total
					recordsWritten += 1

					if self.verbose:
						sys.stdout.write('Writing to database: ' + \
					                     str(int(float(recordsWritten) / float(totalRecords) * 100)) + '%' + "\r")
						sys.stdout.flush()

			#  Insert new hot-topics samplings
			#  Topics are united by a common sample time
			currenttime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
			for i in range(0, len(self.topics)):
				query  = 'INSERT INTO freeweibo_topics(date_sampled, topic, link, n)'
				query += ' VALUES("' + currenttime + '", '
				query +=         '"' + self.topics[i][0] + '", '
				query +=         '"' + self.topics[i][1] + '", '
				query +=               str(i + 1) + ');'

				if self.debugFile:
					fh.write(query + "\n")

				cursor.execute(query)
				self.link.commit()

			self.stopTimer()				#  Report time taken

			if self.stopTime is not None and self.startTime is not None:
				query  = 'INSERT INTO performance_metrics(process, parameter, date_started, sec)'
				query += ' VALUES("collect-freeweibo", ' + str(totalRecords) + ', "'
				query +=   datetime.fromtimestamp(int(self.startTime)).strftime('%Y-%m-%d %H:%M:%S') + '", '
				query +=   str(self.stopTime - self.startTime) + ');'
				cursor.execute(query)
				self.link.commit()

			cursor.close()					#  Close the cursor

			if self.debugFile:				#  Close the debug file
				fh.close()

		else:
			if self.verbose:
				print("\n" + 'NO CONNECTION TO DATABASE! CANNOT SAVE SCRAPED CONTENT!')

		if self.verbose:
			print("\n" + 'Done.')

		return

	#  If they were not provided in the constructor, they may be provided here.
	def setDBcredentials(self, host, uname, pword, table):
		self.dbHost = host
		self.dbUname = uname
		self.dbPword = pword
		self.dbTable = table

	#  Attempt to open a connection to the database using the DB attributes
	def openDB(self):
		if self.dbHost is not None and \
		   self.dbUser is not None and \
		   self.dbPword is not None and \
		   self.dbTable is not None:
			self.link = MySQLdb.connect(self.dbHost, self.dbUser, self.dbPword, self.dbTable)
		elif self.verbose:
			print('Unable to open a DB connection because credentials are missing.')

	#  Close the connection to the database
	def closeDB(self):
		self.link.close()
		return

	def startTimer(self):
		self.startTime = time.mktime(time.gmtime())
		return

	def stopTimer(self):
		self.stopTime = time.mktime(time.gmtime())
		return

	#  Build a lookup table of special character signifiers we'll want to replace before storage/parsing/etc.
	def initReplace(self):
		d = {}
		d['&apos;'] = '\''					#  HTML apostrophe
		d['&#39;'] = '\''					#  Decimal apostrophe
		d['&amp;'] = '&'					#  HTML ampersand
		d['&#38;'] = '&'					#  Decimal ampersand
		d['&quot;'] = '"'					#  HTML double-quote
		d['&#34;'] = '"'					#  Decimal double-quote
		d['&lt;'] = '<'						#  HTML less-than
		d['&#60;'] = '<'					#  Decimal less-than
		d['&gt;'] = '>'						#  HTML greater-than
		d['&#62;'] = '>'					#  Decimal greater-than
		d['&mdash;'] = '--'					#  HTML em-dash
		d['&#8212;'] = '--'					#  Decimal em-dash
		d['&ndash;'] = '--'					#  HTML en-dash
		d['&#8211;'] = '--'					#  Decimal en-dash
		d['&#8210;'] = '--'					#  Decimal figure-dash
		d['&#xa0;'] = ''					#  "Non-breakable Space" symbol is irrelevant to our collections
		d['&#x00a0;'] = ''					#  Four-digit equivalent
		return d

	#  Given a string of text, try determine its language.
	#  (Hardly enough code to justify being its own function, but this used to
	#   be larger. I tried using Google's language detection API, but it enforces
	#   limits and asks for money. If we ever change our resources later, then this
	#   routine would be best off as a sovereign function.)
	def determineLanguage(self, text):

		#return guessLanguage(text)
		if not text:
			return guess_language.UNKNOWN, 0.0

		if isinstance(text, str):
			text = unicode(text, 'utf-8')

		text = guess_language.normalize(text)

		return self.identifyWithConf(text, guess_language.find_runs(text))

	#  A re-write of the _identify function in the guess_language package:
	#  We want to preserve the confidence of the identification.
	def identifyWithConf(self, sample, scripts):
		if len(sample) < 3:
			return guess_language.UNKNOWN, 0.0

		if "Hangul Syllables" in scripts or "Hangul Jamo" in scripts \
		   or "Hangul Compatibility Jamo" in scripts or "Hangul" in scripts:
			return "ko", 1.0

		if "Greek and Coptic" in scripts:
			return "el", 1.0

		if "Katakana" in scripts:
			return "ja", 1.0

		if "CJK Unified Ideographs" in scripts or "Bopomofo" in scripts \
		   or "Bopomofo Extended" in scripts or "KangXi Radicals" in scripts:

			# This is in both Ceglowski and Rideout
			# I can't imagine why...
			#            or "Arabic Presentation Forms-A" in scripts
			return "zh", 1.0

		if "Cyrillic" in scripts:
			return self.checkWithConf( sample, guess_language.CYRILLIC )

		if "Arabic" in scripts or "Arabic Presentation Forms-A" in scripts or "Arabic Presentation Forms-B" in scripts:
			return self.checkWithConf( sample, guess_language.ARABIC )

		if "Devanagari" in scripts:
			return self.checkWithConf( sample, guess_language.DEVANAGARI )


		# Try languages with unique scripts
		for blockName, langName in guess_language.SINGLETONS:
			if blockName in scripts:
				return langName

		if "Latin Extended Additional" in scripts:
			return "vi"

		if "Extended Latin" in scripts:
			latinLang = self.checkWithConf( sample, guess_language.EXTENDED_LATIN )
			if latinLang == "pt":
				return self.checkWithConf(sample, guess_language.PT)
			else:
				return latinLang

		if "Basic Latin" in scripts:
			return self.checkWithConf( sample, guess_language.ALL_LATIN )

		return guess_language.UNKNOWN, 0.0

	#  A re-write of the check function in the guess_language package:
	#  We want to preserve the confidence of the identification.
	def checkWithConf(self, sample, langs):
		if len(sample) < guess_language.MIN_LENGTH:
			return guess_language.UNKNOWN, 0.0

		scores = []
		model = guess_language.createOrderedModel(sample)  # QMap<int,QString>

		greatest = float('-inf')
		least = float('inf')
		for key in langs:
			lkey = key.lower()

			if lkey in guess_language.models:
				d = guess_language.distance(model, guess_language.models[lkey])
				if d > greatest:
					greatest = d
				if d < least:
					least = d
				scores.append( [d, key] )

		#  Normalize scores
		for score in scores:
			#score[0] = float(score[0] - least) / float(greatest - least)
			score[0] = float(score[0]) / float(greatest)

		if not scores:
			return guess_language.UNKNOWN, 0.0

		# we want the lowest score, less distance = greater chance of match
		#    pprint(sorted(scores))
		return min(scores)[1], 1.0 - min(scores)[0]
