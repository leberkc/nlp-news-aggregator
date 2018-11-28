# -*- coding: utf-8 -*-
import re									#  For string clean-up
import sys									#  Used for on-screen notices (print with no carriage return)
import bs4
from bs4 import BeautifulSoup				#  Handles HTML encoding and parsing
import feedparser							#  https://pythonhosted.org/feedparser/
from guess_language import *				#  Pretty lame trigram detector... but it's free
import MySQLdb								#  Used for DB operations
from datetime import datetime				#  Used for time stamping our retrievals
import time									#  Track how long things take

#  The job of this class is to periodically grab a bunch of RSS feeds from a list of sources,
#  parse them and save them to the database. Another routine will perform analysis, which takes
#  a bit more time. The idea here is to constantly be retrieving as much content as possible.
class FeedFetcher:
	#  fetcher = FeedFetcher('localhost', 'censor', 'blockme', 'corpora')
	def __init__(self, dbHost=None, dbUser=None, dbPword=None, dbTable=None):
		self.feeds = []						#  List of RSS URLs

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

	#  Iterate over feeds and build a giant list
	def fetch(self):
		feedCtr = 1
		records = []
		for feed in self.feeds:
			if self.verbose:
				print(str(feedCtr) + '.  ' + feed)
			records += self.fetchFeedArticles(feed)
			feedCtr += 1

		return records

	#  Save the given list of dictionary objects to the database, checking each time that
	#  we do not already have one. URLs are considered unique identifiers.
	#  Return the number of UNIQUE records added
	def save(self, docs):
		if self.link is not None:			#  Attempt to save to the DB

			if self.debugFile:
				fh = open('rss-' + str(time.time()) + '.debug', 'w')

			totalRecords = len(docs)
			recordsWritten = 0				#  Track progress

			if self.verbose:
				print("\n" + str(totalRecords) + " articles scraped (not all may be unique)\n")
				sys.stdout.write('Writing to database: 0%' + "\r")
				sys.stdout.flush()

			cursor = self.link.cursor(MySQLdb.cursors.DictCursor)
			for doc in docs:

				foundUnique = False			#  Find out whether we have this article already by looking up
											#  both the url and the content message digests.
				if doc['hash_url'] is not None and doc['hash_content'] is not None:
					query  = 'SELECT * FROM articles'
					query += ' WHERE hash_url = ' + str(doc['hash_url'])
					query += ' AND hash_content = ' + str(doc['hash_content']) + ';'
					cursor.execute(query)
					result = cursor.fetchall()
					if len(result) == 0:
						foundUnique = True
					else:					#  If this is >= 1, then we either have a double hash collision
											#  (possible but extremely unlikely) or we have already collected
											#  this article (extremely likely).
						#  If we have collected this article already, then check to see whether it is simply being
						#  resourced: it may be helpful to know which articles get re-reported on which forums.
						for row in result:
							aID = int(row['kp'])
							query  = 'SELECT * FROM article_source'
							query += ' WHERE article_id = ' + str(aID)
							query += ' AND source = "' + doc['rss'] + '";'
							cursor.execute(query)
							res = cursor.fetchall()
											#  Add this article-source pair only if it does not already exist
							if len(res) == 0:
								query  = 'INSERT INTO article_source(article_id, source)'
								query += ' VALUES(' + str(aID) + ', "' + doc['rss'] + '");'
								cursor.execute(query)

				if foundUnique:				#  Add record to the database (accounting for its being potentially partial)
					query = 'INSERT INTO articles('
					vals = ''

					#  URL is ASCII
					if doc['url'] is not None:
						query += 'url, '
						vals += '"' + doc['url'] + '", '
					#  HASH_URL is an unsigned long int
					if doc['hash_url'] is not None:
						query += 'hash_url, '
						vals += str(doc['hash_url']) + ', '
					#  HASH_CONTENT is an unsigned long int
					if doc['hash_content'] is not None:
						query += 'hash_content, '
						vals += str(doc['hash_content']) + ', '
					#  TITLE is UNICODE
					if doc['title'] is not None:
						query += 'title, '
						#vals += u'"' + doc['title'].encode('utf-8').decode('unicode-escape') + u'", '
						vals += '"' + doc['title'] + '", '
					#  CONTENT is UNICODE
					if doc['text'] is not None:
						query += 'content, '
						#vals += u'"' + doc['text'].encode('utf-8').decode('unicode-escape') + u'", '
						vals += '"' + doc['text'] + '", '
					#  SUMMARY is UNICODE
					if doc['summary'] is not None:
						query += 'summary, '
						#vals += u'"' + doc['summary'].encode('utf-8').decode('unicode-escape') + u'", '
						vals += '"' + doc['summary'] + '", '
					#  KEYWORD is UNICODE
					if doc['keyword'] is not None:
						query += 'keyword, '
						#vals += u'"' + doc['keyword'].encode('utf-8').decode('unicode-escape') + u'", '
						vals += '"' + doc['keyword'] + '", '
					#  LANG-CLAIMED is UNICODE
					if doc['lang-claimed'] is not None:
						query += 'lang_claimed, '
						#vals += u'"' + doc['lang-claimed'].encode('utf-8').decode('unicode-escape') + u'", '
						vals += '"' + doc['lang-claimed'] + '", '
					#  LANG-DETECTED is ASCII
					if doc['lang-detected'] is not None:
						query += 'lang_detected, '
						vals += '"' + doc['lang-detected'] + '", '
					#  LANG-DETECTION CONFIDENCE is ASCII
					if doc['lang-confidence'] is not None:
						query += 'confidence, '
						vals += str(doc['lang-confidence']) + ', '
					if doc['pub-date'] is not None:
						query += 'pub_date, '
						vals += '"' + doc['pub-date'] + '", '
					if doc['date-retrieved'] is not None:
						query += 'ret_date'
						vals += '"' + doc['date-retrieved'].strftime('%Y-%m-%d %H:%M:%S') + '"'

					query += ') VALUES(' + vals + ');'

					if self.debugFile:
						fh.write(query + "\n")

					cursor.execute(query)
					newRow = cursor.lastrowid

					query  = 'INSERT INTO article_source(article_id, source)'
					query += ' VALUES(' + str(newRow) + ', "' + doc['rss'] + '");'
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

			self.stopTimer()				#  Report time taken

			if self.stopTime is not None and self.startTime is not None:
				query  = 'INSERT INTO performance_metrics(process, parameter, date_started, sec)'
				query += ' VALUES("collect-rss", ' + str(totalRecords) + ', "'
				query +=   datetime.fromtimestamp(int(self.startTime)).strftime('%Y-%m-%d %H:%M:%S') + '", '
				query +=   str(self.stopTime - self.startTime) + ');'
				cursor.execute(query)
				self.link.commit()

			cursor.close()					#  Close the cursor

			if self.debugFile:
				fh.close()

		else:
			if self.verbose:
				print("\n" + 'NO CONNECTION TO DATABASE! CANNOT SAVE SCRAPED CONTENT!')

		if self.verbose:
			print("\n" + 'Done.')

		return

	#  Given a feed (a URL string) retrieve all its entries.
	#  Then, for each entry, build a list of its words, also saving some of its data like
	#  publication date, URL, title, language, etc.
	#
	#  This function returns a list of dictionaries, one for each article:
	#  [ { 'url', 'hash_url', 'title', 'text', 'hash_content', 'summary', 'keyword', lang-claimed', 'lang-detected', 'lang-confidence', 'pub-date', 'date-retrieved' },
	#    { 'url', 'hash_url', 'title', 'text', 'hash_content', 'summary', 'keyword', lang-claimed', 'lang-detected', 'lang-confidence', 'pub-date', 'date-retrieved' },
	#      ...
	#  ]
	#  url:            The URL of this article
	#  hash_url:       Message digest of URL
	#  title:          The title of the article
	#  text:           The text of the article, as a single string of natural language
	#                  (Beautiful Soup removes the markup)
	#  hash_content:   Message digest of article
	#  summary:        A summary of the article
	#  keyword:        If provided
	#  lang-claimed:   The language in which the article says it is written, if this was included
	#  lang-detected:  The language our trigram-guesser believes applies to this article
	#  lang-confidence:Confidence about this language categorization, [0.0, 1.0]
	#  pub-date:       The date the article was published
	#  date-retrieved: Timestamp of when this article was scraped by us
	def fetchFeedArticles(self, feed):
		docs = []
		#  One feed yields one or more entries.
		#  RSSstruct is a list of dictionaries, each keyed by RSS attributes
		#  such as title, content (itself a list of dictionaries), summary_detail,
		#  keyword, etc...
		RSSstruct = feedparser.parse(feed)
		entryCtr = 1
		for entry in RSSstruct['entries']:
			#  Use BeautifulSoup to retrieve an encoding-agnostic plaintext string of the article attributes.
			#  We include ['content']['value'], ['title'], ['summary'], ['keyword'].
			#  (We also check ['content']['language']. This field is often left blank, and there is no guarantee
			#   that the RSS creator used 'en' instead of 'English', 'english', or... 'inglush', but worth checking.)
			#  (There's also a field named 'liability'. What's that?)

			articleContent = None			#  Article content
			articleTitle = None				#  Article's title
			articleSummary = None			#  The summary given for this article
			articleSummaryDetail = None		#  Accommodate China Daily specs (see note below, 21NOV17)
			articleKeyword = None			#  The keyword for this article, if provided
			lang = None						#  Language detected using trigrams
			langConfidence = None			#  The trigram-detector's confidence in its verdict
			langClaimed = None				#  Language claimed by the article (not always given)

			#  21NOV17: I noticed that many of the articles actually written in Chinese use a different
			#  format for their text and tags. The main content seems to be labeled "summary," and the
			#  summary seems to be labeled "summary_detail." If summary_detail is present and content
			#  is None, then save summary to content and save summary_detail to summary.

			#  Scrape article content
			if 'content' in entry:
				for e in entry['content']:
					if 'value' in e and e['value'] is not None:
						articleContent = BeautifulSoup(e['value'].encode('utf-8'), 'html.parser').get_text()
					if 'language' in e and e['language'] is not None:
						langClaimed = BeautifulSoup(e['language'].encode('utf-8'), 'html.parser').get_text()

			#  Scrape article title
			if 'title' in entry and entry['title'] is not None:
				articleTitle = BeautifulSoup(entry['title'].encode('utf-8'), 'html.parser').get_text()

			#  Scrape article summary
			if 'summary' in entry and entry['summary'] is not None:
				articleSummary = BeautifulSoup(entry['summary'].encode('utf-8'), 'html.parser').get_text()

			#  Is 'summary_detail' present?
			if 'summary_detail' in entry and entry['summary_detail'] is not None:
				if 'value' in entry['summary_detail'] and entry['summary_detail']['value'] is not None:
					articleSummaryDetail = BeautifulSoup(entry['summary_detail']['value'].encode('utf-8'), 'html.parser').get_text()

			#  Scrape article keyword(s)
			if 'keyword' in entry and entry['keyword'] is not None:
				articleKeyword = BeautifulSoup(entry['keyword'].encode('utf-8'), 'html.parser').get_text()

			#  Probe various attributes (in order of preference) to determine which language the feed contains
			if lang is None:
				if articleContent is not None:
					lang, langConfidence = self.determineLanguage(articleContent)
				elif articleSummary is not None:
					lang, langConfidence = self.determineLanguage(articleSummary)
				elif articleTitle is not None:
					lang, langConfidence = self.determineLanguage(articleTitle)
				elif articleKeyword is not None:
					lang, langConfidence = self.determineLanguage(articleKeyword)
				else:
					lang = 'UNKNOWN'
					langConfidence = 0.0

			'''
			#  This bit of code rendered visible parsings which did NOT contain 'content'.
			#  Enable this again if scrapings do not seem to yield what they should.
			if articleContent is None:
				fh = open('analyze-' + str(time.time()) + '.txt', 'w')
				fstr = ''
				for k, v in entry.items():
					safe = repr(v)
					safe = re.sub(r'\"', '\\\"', safe)
					safe = re.sub(r'\u', '\\u', safe)
					fstr += str(k) + "\t" + safe + "\n"
				fh.write(fstr)
				fh.close()
			'''

			#  Remove line breaks AFTER we've attempted to identify the language
			if self.removeLB:
				if articleContent is not None:
					articleContent = ' '.join(articleContent.splitlines())
				if articleSummary is not None:
					articleSummary = ' '.join(articleSummary.splitlines())
				if articleSummaryDetail is not None:
					articleSummaryDetail = ' '.join(articleSummaryDetail.splitlines())
				if articleTitle is not None:
					articleTitle = ' '.join(articleTitle.splitlines())
				if articleKeyword is not None:
					articleKeyword = ' '.join(articleKeyword.splitlines())

			#  Find-and-replace web-formatted characters
			if self.replaceSpecial:
				for k, v in self.replaceDict.items():
					if articleContent is not None:
						articleContent = re.sub(k, v, articleContent)
					if articleSummary is not None:
						articleSummary = re.sub(k, v, articleSummary)
					if articleSummaryDetail is not None:
						articleSummaryDetail = re.sub(k, v, articleSummaryDetail)
					if articleTitle is not None:
						articleTitle = re.sub(k, v, articleTitle)
					if articleKeyword is not None:
						articleKeyword = re.sub(k, v, articleKeyword)

				#  &#nnn;  means the number is DECIMAL     convert to \ummm where mmm is hex for nnn
				#  &#xnnn; means the number is HEXADECIMAL convert to \unnn
				if articleContent is not None:
					articleContent = re.sub(r'&#(\d+);', lambda m: r'\u' + "{0:#0{1}x}".format(int(m.group()[2:-1]), 6)[2:], articleContent)
					articleContent = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: r'\u' + "{0:#0{1}x}".format(int(m.group(1), 16), 6)[2:], articleContent)
				if articleSummary is not None:
					articleSummary = re.sub(r'&#(\d+);', lambda m: r'\u' + "{0:#0{1}x}".format(int(m.group()[2:-1]), 6)[2:], articleSummary)
					articleSummary = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: r'\u' + "{0:#0{1}x}".format(int(m.group(1), 16), 6)[2:], articleSummary)
				if articleSummaryDetail is not None:
					articleSummaryDetail = re.sub(r'&#(\d+);', lambda m: r'\u' + "{0:#0{1}x}".format(int(m.group()[2:-1]), 6)[2:], articleSummaryDetail)
					articleSummaryDetail = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: r'\u' + "{0:#0{1}x}".format(int(m.group(1), 16), 6)[2:], articleSummaryDetail)
				if articleTitle is not None:
					articleTitle = re.sub(r'&#(\d+);', lambda m: r'\u' + "{0:#0{1}x}".format(int(m.group()[2:-1]), 6)[2:], articleTitle)
					articleTitle = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: r'\u' + "{0:#0{1}x}".format(int(m.group(1), 16), 6)[2:], articleTitle)
				if articleKeyword is not None:
					articleKeyword = re.sub(r'&#(\d+);', lambda m: r'\u' + "{0:#0{1}x}".format(int(m.group()[2:-1]), 6)[2:], articleKeyword)
					articleKeyword = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: r'\u' + "{0:#0{1}x}".format(int(m.group(1), 16), 6)[2:], articleKeyword)

			#  Display notifications to the screen about what we're scraping
			scrapeNotice = unicode(str(entryCtr) + '.  ')
			outstr = u''
			#  Title may have extra-ASCII characters; clean those out for display
			if articleTitle is not None and len(articleTitle) > 0:
				#  Directed quotation marks jam up English,
				#  so test for them specifically when printing to screen.
				#  (This does not affect what is stored in the database).
				if 128 in [ord(x) for x in list(articleTitle)]:
					outstr += u"\t" + scrapeNotice + u'Title: ' + ''.join( [x for x in list(articleTitle) if ord(x) < 128] ) + u"\n"
				else:
					outstr += u"\t" + scrapeNotice + u'Title: ' + unicode(articleTitle) + u"\n"
			#  URLs are confined to ASCII
			if 'link' in entry and entry['link'] is not None and len(entry['link']) > 0:
				if len(outstr) > 0:
					outstr += u"\t" + (u' ' * len(scrapeNotice)) + u'URL: ' + entry['link'] + u"\n"
				else:
					outstr += u"\t" + scrapeNotice + u'URL: ' + entry['link'] + u"\n"
			#  Time stamps do not stray beyond ASCII character set
			if 'published' in entry and entry['published'] is not None and len(entry['published']) > 0:
				if len(outstr) > 0:
					outstr += u"\t" + (u' ' * len(scrapeNotice)) + u'Published: ' + entry['published'] + u"\n"
				else:
					outstr += u"\t" + scrapeNotice + u'Published: ' + entry['published'] + u"\n"
			#  Detected strings WILL NOT contain tricky characters
			if len(outstr) > 0:
				outstr += u"\t" + (u' ' * len(scrapeNotice)) + u'Detected: ' + lang + u", " + str(langConfidence) + u"\n"
			else:
				outstr += u"\t" + scrapeNotice + u'Detected: ' + lang + u", " + str(langConfidence) + u"\n"

			if self.verbose:
				print(outstr)

			#  Pack up all the information we want to save (anticipating that it may be incomplete).
			#  Also, notice that anything which comes from the article is being sanitized using repr().
			#  This is to account for all languages. Just remember that they are stored this way when
			#  you retrieve them from the DB.
			doc = {}						#  Build new dictionary object
			doc['rss'] = feed				#  Save source for reference
			if 'link' in entry:				#  Add URL
				doc['url'] = entry['link']	#  Hash URL
				doc['hash_url'] = hash(doc['url']) % ((sys.maxsize + 1) * 2)
			else:
				doc['url'] = None
				doc['hash_url'] = None

			if articleTitle is not None:	#  Add article title (render for DB storage)
				safe = repr(articleTitle)[2:-1]
				safe = re.sub(r'\"', '\\\"', safe)
				safe = re.sub(r'\u', '\\u', safe)
				doc['title'] = safe
			else:
				doc['title'] = None

			if articleContent is not None:	#  Add article text (render for DB storage)
				safe = repr(articleContent)[2:-1]
				safe = re.sub(r'\"', '\\\"', safe)
				safe = re.sub(r'\u', '\\u', safe)
				doc['text'] = safe			#  Hash text
				doc['hash_content'] = hash(doc['text']) % ((sys.maxsize + 1) * 2)
			elif articleSummary is not None and articleSummaryDetail is not None:
				safe = repr(articleSummary)[2:-1]
				safe = re.sub(r'\"', '\\\"', safe)
				safe = re.sub(r'\u', '\\u', safe)
				doc['text'] = safe			#  Hash text
				doc['hash_content'] = hash(doc['text']) % ((sys.maxsize + 1) * 2)
			elif articleTitle is not None:
				doc['text'] = None
				#  We only use the hashed title if other text was unavailable
				#  (Some Chinese RSS feeds are packaged differently)
				doc['hash_content'] = hash(doc['title']) % ((sys.maxsize + 1) * 2)
			else:
				doc['text'] = None
				doc['hash_content'] = None
											#  Add article summary (render for DB storage)
			if articleSummary is not None and articleSummaryDetail is None:
				safe = repr(articleSummary)[2:-1]
				safe = re.sub(r'\"', '\\\"', safe)
				safe = re.sub(r'\u', '\\u', safe)
				doc['summary'] = safe
			elif articleSummaryDetail is not None:
				safe = repr(articleSummaryDetail)[2:-1]
				safe = re.sub(r'\"', '\\\"', safe)
				safe = re.sub(r'\u', '\\u', safe)
				doc['summary'] = safe
			else:
				doc['summary'] = None

			if articleKeyword is not None:	#  Add keyword (render for DB storage)
				safe = repr(articleKeyword)[2:-1]
				safe = re.sub(r'\"', '\\\"', safe)
				safe = re.sub(r'\u', '\\u', safe)
				doc['keyword'] = safe
			else:
				doc['keyword'] = None

			if langClaimed is not None:		#  Add language claimed (render for DB storage)
				safe = repr(langClaimed)[2:-1]
				safe = re.sub(r'\"', '\\\"', safe)
				safe = re.sub(r'\u', '\\u', safe)
				doc['lang-claimed'] = safe
			else:
				doc['lang-claimed'] = None

			if lang == 'UNKNOWN':			#  Add language detected
				doc['lang-detected'] = None
			else:
				doc['lang-detected'] = lang

			if lang == 'UNKNOWN':			#  Add language-detection confidence
				doc['lang-confidence'] = 0.0
			else:
				doc['lang-confidence'] = langConfidence

			if 'published' in entry:		#  Add date published
				doc['pub-date'] = entry['published']
			else:
				doc['pub-date'] = None
											#  Add date retrieved
			doc['date-retrieved'] = datetime.now()

			docs.append(doc)				#  Add new record to list
			entryCtr += 1					#  Update count

		return docs

	#  Pull a list of news feeds to check for new articles
	#  Returns a list of URL strings:
	#  e.g. [
	#         'http://www.chinadaily.com.cn/rss/china_rss.xml',
	#         'http://www.chinadaily.com.cn/rss/bizchina_rss.xml',
	#         ...
	#       ]
	def getFeeds(self):
		if self.link is not None:

			self.startTimer()

			cursor = self.link.cursor(MySQLdb.cursors.DictCursor)
			query = 'SELECT feed FROM rss WHERE enabled = TRUE;'
			cursor.execute(query)
			result = cursor.fetchall()
			if len(result) > 0:
				for row in result:
					self.feeds.append(row['feed'])
			elif self.verbose:
				print('No RSS feeds found.')
			cursor.close()
		elif self.verbose:
			print('No target RSS feeds found.')

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
