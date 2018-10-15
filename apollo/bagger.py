# -*- coding: utf-8 -*-
import time							#  Track how long things take
import sys							#  Used for re-writable screen output
import re							#  For find-and-replace work
import math
import MySQLdb						#  Used for DB operations
from datetime import datetime		#  Used for time stamping our retrievals
import nltk
from nltk.tokenize import word_tokenize
from nltk.parse import stanford
from nltk.tokenize.stanford_segmenter import StanfordSegmenter

class ArticleBagger:
	#  bagger = ArticleBagger(50, 'localhost', 'censor', 'blockme', 'corpora')
	def __init__(self, lim=None, dbHost=None, dbUser=None, dbPword=None, dbTable=None):
		self.limit = lim			#  Process records [rangea, rangeb] inclusive
		self.useConfidence = True	#  Whether to selectively pull records according to diagnostic confidence
		self.confidence = 0.25		#  Confidence threshold: only process records with language-identification
									#  confidence greater than or equal to this number.
		self.languageFilter = None	#  If a specific language is requested, store a string representation here

		self.segmenter = None		#  Segmentor tokenizes words for languages in which characters run together
									#  This may not always be necessary, so we will not initialize it here.
									#  A separate function is used for that.

		self.link = None			#  MySQL link
		self.dbHost = dbHost		#  String indicating database host
		self.dbUser = dbUser		#  String indicating database host
		self.dbPword = dbPword		#  String indicating database host
		self.dbTable = dbTable		#  String indicating database host

		self.procId = None			#  Process ID, mirrored in the 'baggings' table
		self.raws = []				#  List of raw objects:
		#  [ { 'kp', 'url', 'title', 'text', 'summary', 'keyword', 'lang-claimed', 'lang-detected', 'confidence', 'pub-date', 'date-retrieved' },
		#    { 'kp', 'url', 'title', 'text', 'summary', 'keyword', 'lang-claimed', 'lang-detected', 'confidence', 'pub-date', 'date-retrieved' },
		#      ...
		#  ]
		#  kp:			   Key Primero: this record's unique numerical identifier
		#  url:            The URL of this article
		#  title:          The title of the article
		#  text:           The text of the article, as a single string of natural language (Beautiful Soup removes the markup)
		#  summary:        A summary of the article
		#  keyword:        If provided
		#  lang-claimed:   The language in which the article says it is written, if this was included
		#  lang-detected:  The language our trigram-guesser believes applies to this article
		#  confidence:     A measure of how sure the trigram-detector was about the language it diagnosed.
		#  pub-date:       The date the article was published
		#  date-retrieved: Timestamp of when this article was scraped by us
		self.bags = []				#  Bags of words, one corresponding to each record in raws

		self.verbose = False		#  Whether to print progress to screen

		self.startTime = None		#  Time this routine
		self.stopTime = None

		return

	#  Assumes raws[] and bags[] have content
	#  BATCH saves update the timing table
	def batchSave(self):
		if self.link is not None:	#  Attempt to save to the DB
			cursor = self.link.cursor(MySQLdb.cursors.DictCursor)

			if self.verbose:
				print("\n")
				sys.stdout.write('Updating database: 0%' + "\r")
				sys.stdout.flush()

			for i in range(0, len(self.raws)):
									#  Convert Unicode strings to DB-safe representations
									#  u'montclair'          ==> 'montclair'
									#  u'\u4f0a\u6717\u4eba' ==> '\u4f0a\u6717\u4eba'
				safe = [repr(x)[2:-1] for x in self.bags[i]]
				safe = [re.sub(r'\"', '\\\"', x) for x in safe]
				safe = [re.sub(r'\u', '\\u', x) for x in safe]

				query  = 'UPDATE articles SET'
				query += ' bag_of_words = "' + "\t".join(safe) + '",'
				query += ' processed = TRUE'
				query += ' WHERE kp = ' + str(self.raws[i]['kp']) + ';'
				cursor.execute(query)
				self.link.commit()

				if self.verbose:
					sys.stdout.write('Updating database: ' + \
					                 str(int(float(i + 1) / float(len(self.raws)) * 100)) + '%' + "\r")
					sys.stdout.flush()

			if self.verbose:
				print("\n")

			query = 'UPDATE baggings SET completed = TRUE WHERE kp = ' + str(self.procId) + ';'
			cursor.execute(query)
			self.link.commit()

			#  Officially, our work is over; the rest is bookkeeping
			self.stopTimer()

			#  Add an account of this run's performance
			if self.stopTime is not None and self.startTime is not None:
				query  = 'INSERT INTO performance_metrics(process, parameter, date_started, sec)'
				query += ' VALUES("bagged", ' + str(len(self.raws)) + ', "'
				query +=   datetime.fromtimestamp(int(self.startTime)).strftime('%Y-%m-%d %H:%M:%S') + '", '
				query +=   str(self.stopTime - self.startTime) + ');'
				cursor.execute(query)
				self.link.commit()

			cursor.close()
		elif self.verbose:
			print('No database connection; unable to save.')
		return

	#  Retrieve, process, and save n records
	def batchClean(self, n=None):
		if n is None:
			n = self.limit

		if n is not None:
			if self.link is not None:

				self.startTimer()

				#  Declare a new cleaning process
				self.declareProc()

				#  Pull n records
				self.pull(n)

				#  Mark the pulled records
				self.mark()

				#  One article => one "bag of words"
				rctr = 1
				for record in self.raws:
					outhdr  = str(rctr) + ' / ' + str(len(self.raws)) + ': '
					outstr  = 'bag-of-words for article ' + str(record['kp']) + "\n"
					outstr += ' ' * len(outhdr) + record['title'] + "\n"

					bow = []			#  Fresh for each article
					targets = []		#  Remember constant assumption that records are incomplete
					if record['title'] is not None:
						targets.append(record['title'])
					if record['text'] is not None:
						targets.append(record['text'])
					if record['summary'] is not None:
						targets.append(record['summary'])
					if record['keyword'] is not None:
						targets.append(record['keyword'])

					for target in targets:
						bow += [x for x in self.process(record['lang-detected'], target, self.segmenter)]

					outstr += ' ' * len(outhdr) + str(len(bow)) + ' words' + "\n"
					if self.verbose:
						print(outhdr + outstr)

					self.bags.append(bow)

					rctr += 1
			else:
				print('No connection to the database has been established.')
		else:
			print('Range of records is not specified.')

		return

	#  Parse/Tokenize/Segment text according to language
	#  Return a "bag of words" as a list of unicode strings, made lower-case where appropriate
	#  e.g. "The quick, brown fox jumped over the lazy dog."
	#    => [u'the', u'quick', u',', u'brown', u'fox', u'jumped', u'over', u'the', u'lazy', u'dog', u'.']
	#  22JAN18: LEAVE THE STOPWORDS IN THE BAG!
	#           They are easy to remove, so only do this later at the user's request.
	#  07FEB18: LEAVE THE PUNCTUATION IN THE BAG!
	#           Whether or not it's removed is application specific.
	#           For instance, '!!!!!!!' is very telling in sentiment analysis
	def process(self, lang, text, segmenter):
		#  Arabic
		if lang == 'ar':
			#parser.model_path = 'edu/stanford/nlp/models/lexparser/arabicFactored.ser.gz'
			#return [x for x in segmenter.segment(text) if x not in stopwords.words('arabic')]
			return segmenter.segment(text)
		#  Danish
		#  Is Danish case-sensitive?
		elif lang == 'da':
			#return [x for x in nltk.wordpunct_tokenize(text) if x not in stopwords.words('danish')]
			return word_tokenize(text)
		#  German
		#  Die deutsche Sprache ist Gross- / Kleinschreibung-unterscheidend!
		#  Man darf nicht .lower() benutzen!
		elif lang == 'de':
			#return [x for x in nltk.wordpunct_tokenize(text) if x not in stopwords.words('german')]
			return word_tokenize(text)
		#  Spanish
		elif lang == 'es':
			#return [x.lower() for x in nltk.wordpunct_tokenize(text) if x.lower() not in stopwords.words('spanish')]
			return [x.lower() for x in word_tokenize(text)]
		#  Finnish
		elif lang == 'fi':
			#return [x.lower() for x in nltk.wordpunct_tokenize(text) if x.lower() not in stopwords.words('finnish')]
			return [x.lower() for x in word_tokenize(text)]
		#  French
		elif lang == 'fr':
			#return [x.lower() for x in nltk.wordpunct_tokenize(text) if x.lower() not in stopwords.words('french')]
			return [x.lower() for x in word_tokenize(text)]
		#  Hungarian
		elif lang == 'hu':
			#return [x.lower() for x in nltk.wordpunct_tokenize(text) if x.lower() not in stopwords.words('hungarian')]
			return [x.lower() for x in word_tokenize(text)]
		#  Italian
		elif lang == 'it':
			#return [x.lower() for x in nltk.wordpunct_tokenize(text) if x.lower() not in stopwords.words('italian')]
			return [x.lower() for x in word_tokenize(text)]
		#  Kazakh
		elif lang == 'kk':
			#return [x.lower() for x in nltk.wordpunct_tokenize(text) if x.lower() not in stopwords.words('kazakh')]
			return [x.lower() for x in word_tokenize(text)]
		#  Dutch
		#  Is Dutch case-sensitive?
		elif lang == 'nl':
			#return [x for x in nltk.wordpunct_tokenize(text) if x not in stopwords.words('dutch')]
			return [x for x in word_tokenize(text)]
		#  Norwegian
		elif lang == 'no':
			#return [x.lower() for x in nltk.wordpunct_tokenize(text) if x.lower() not in stopwords.words('norwegian')]
			return [x.lower() for x in word_tokenize(text)]
		#  Portuguese (Brazilian and Portuguese)
		elif lang == 'pt_BR' or lang == 'pt_PT':
			#return [x.lower() for x in nltk.wordpunct_tokenize(text) if x.lower() not in stopwords.words('portuguese')]
			return [x.lower() for x in word_tokenize(text)]
		#  Romanian
		elif lang == 'ro':
			#return [x.lower() for x in nltk.wordpunct_tokenize(text) if x.lower() not in stopwords.words('romanian')]
			return [x.lower() for x in word_tokenize(text)]
		#  Russian
		elif lang == 'ru':
			#return [x.lower() for x in nltk.wordpunct_tokenize(text) if x.lower() not in stopwords.words('russian')]
			return [x.lower() for x in word_tokenize(text)]
		#  Turkish
		elif lang == 'tr':
			#return [x.lower() for x in nltk.wordpunct_tokenize(text) if x.lower() not in stopwords.words('turkish')]
			return [x.lower() for x in word_tokenize(text)]
		#  Swedish
		elif lang == 'sv':
			#return [x.lower() for x in nltk.wordpunct_tokenize(text) if x.lower() not in stopwords.words('swedish')]
			return [x.lower() for x in word_tokenize(text)]
		#  Chinese
		elif lang == 'zh':
			#  No stopwords list for Chinese as of 04NOV17.

			#  11DEC17: Parser is not handling Latin characters correctly.
			#  Given this unicode-escaped string "\u4f0a\u6717\u4ebaMartin\u5728\u5317\u4eac ..."
			#  it will segment like this:
			#  \u4f0a\u6717\u4eba, M, a, r, t, i, n, \u5728, \u5317\u4eac, ...
			#  This happens because the Chinese parser does not know what to do with the string "Martin".
			#  Therefore, we will first scan for any Western substrings.
			#  This is the job of the function isWestern().
			chunks = ['']
			charSetMap = []							#  Track chunk encoding
			chars = list(text)						#  Iterate character by character
			if self.isWestern(chars[0]):			#  In which character set do we begin iteration?
				runningUnicode = False
				charSetMap.append(False)
			else:
				runningUnicode = True
				charSetMap.append(True)

			#  Notice we are proceeding on the assumption that Chinese to the left and right of substrings
			#  like "Martin" can be segmented out of context.
			for i in range(0, len(chars)):
				currUnicode = not self.isWestern(chars[i])
				if currUnicode == runningUnicode:	#  If they still agree, add this to the current chunk
					chunks[-1] += chars[i]
				else:								#  Otherwise, create a new chunk and add to that
					chunks.append('')
					chunks[-1] += chars[i]
					runningUnicode = currUnicode	#  Flip-flop the character set indicator
					charSetMap.append( not charSetMap[-1] )

			#  Now iterate over the chunks and segment only those chunks in Chinese (unicode)
			ret = []								#  The segmented list we will return
			for i in range(0, len(chunks)):
				if charSetMap[i]:					#  If this is Chinese (unicode), then pass to the segmenter
					ret += segmenter.segment(chunks[i]).split()
				else:								#  If this is Western, then treat it like English:
													#  tokenize, pull stopwords, and make lower-case
					#ret += [x.lower() for x in word_tokenize(chunks[i]) if x.lower() not in stopwords.words('english')]
					ret += [x.lower() for x in word_tokenize(chunks[i])]

			#  11DEC17:
			#  Segmenter results from the original method:
			#           '\u4f0a\u6717\u4eba', 'M', 'a', 'r', 't', 'i', 'n', '\u5728', '\u5317\u4eac', '\u5c55\u793a',
			#           '\u81ea\u5df1', '\u5bb6\u65cf', '\u7684', '\u5730\u6bef', '\u6536\u85cf',
			#           '\uff0c', '\u4e5f', '\u4f1a', '\u628a', '\u8fd9\u4e9b', '\u5730\u6bef',
			#           '\u5356', '\u7ed9', '\u8bc6\u8d27', '\u7684', '\u4eba', '\u3002',
			#           '\u5730\u6bef', '\u7f16\u7ec7', '\u662f', '\u4f0a\u6717', '\u7684',
			#           '\u4f20\u7edf', '\u827a\u672f', '\uff0c', 'M', 'a', 'r', 't', 'i', 'n', '\u5176\u5b9e',
			#           '\u66f4', '\u60f3', '\u901a\u8fc7', '\u5730\u6bef', '\u751f\u610f',
			#           '\u4f20\u64ad', '\u4f0a\u6717', '\u6587\u5316', '\u3002'
			#  Segmenter results from the revised method:
			#           '\u4f0a\u6717\u4eba', 'Martin', '\u5728', '\u5317\u4eac', '\u5c55\u793a',
			#           '\u81ea\u5df1', '\u5bb6\u65cf', '\u7684', '\u5730\u6bef', '\u6536\u85cf',
			#           '\uff0c', '\u4e5f', '\u4f1a', '\u628a', '\u8fd9\u4e9b', '\u5730\u6bef',
			#           '\u5356', '\u7ed9', '\u8bc6\u8d27', '\u7684', '\u4eba', '\u3002',
			#           '\u5730\u6bef', '\u7f16\u7ec7', '\u662f', '\u4f0a\u6717', '\u7684',
			#           '\u4f20\u7edf', '\u827a\u672f', '\uff0c', 'Martin', '\u5176\u5b9e',
			#           '\u66f4', '\u60f3', '\u901a\u8fc7', '\u5730\u6bef', '\u751f\u610f',
			#           '\u4f20\u64ad', '\u4f0a\u6717', '\u6587\u5316', '\u3002'

			#parser.model_path = 'edu/stanford/nlp/models/lexparser/chineseFactored.ser.gz'
			return ret

		#  English is the default
		#return [x.lower() for x in nltk.wordpunct_tokenize(text) if x.lower() not in stopwords.words('english')]
		return [x.lower() for x in word_tokenize(text)]

	#  Mark the records we pulled as "the intended" of this cleaning process
	def mark(self):
		#  Only proceed if there were in fact any records pulled:
		#  What if we're all caught up?
		if len(self.raws) > 0:
			#  Declare dictionary-type cursor (assoc-arrays)
			cursor = self.link.cursor(MySQLdb.cursors.DictCursor)

			query = 'UPDATE articles SET marked_by_proc = ' + str(self.procId) + ' WHERE '
			for i in range(0, len(self.raws)):
				if i < len(self.raws) - 1:
					query += 'kp = ' + str(self.raws[i]['kp']) + ' OR '
				else:
					query += 'kp = ' + str(self.raws[i]['kp']) + ';'
			cursor.execute(query)
			self.link.commit()

			if self.verbose:
				print('Marked ' + str(len(self.raws)) + ' records for cleaning process #' + str(self.procId))

			cursor.close()
		elif self.verbose:
				print('Marked ' + str(len(self.raws)) + ' records for cleaning process #' + str(self.procId))
		return

	#  Pull n records into our local list (self.raws)
	def pull(self, n):
		#  Declare dictionary-type cursor (assoc-arrays)
		cursor = self.link.cursor(MySQLdb.cursors.DictCursor)

		if self.useConfidence:
			query  = 'SELECT * FROM articles'
			query += ' WHERE processed = FALSE AND confidence >= ' + str(self.confidence)
			if self.languageFilter is not None:
				query += ' AND (lang_claimed = "' + self.languageFilter + '" OR lang_detected = "' + self.languageFilter + '")'
			query += ' ORDER BY pub_date ASC LIMIT ' + str(n) + ';'
		else:
			query  = 'SELECT * FROM articles'
			query += ' WHERE processed = FALSE'
			if self.languageFilter is not None:
				query += ' AND (lang_claimed = "' + self.languageFilter + '" OR lang_detected = "' + self.languageFilter + '")'
			query += ' ORDER BY pub_date ASC LIMIT ' + str(n) + ';'
		cursor.execute(query)
		result = cursor.fetchall()
		for row in result:
			self.raws.append( {} )
			self.raws[-1]['kp'] = int(row['kp'])					#  Int
			self.raws[-1]['url'] = row['url']						#  ASCII string

			self.raws[-1]['title'] = row['title']					#  Unicode-escaped
			if self.raws[-1]['title'] is not None:
				self.raws[-1]['title'] = self.raws[-1]['title'].decode('unicode-escape')

			self.raws[-1]['text'] = row['content']					#  Unicode-escaped
			if self.raws[-1]['text'] is not None:
				self.raws[-1]['text'] = self.raws[-1]['text'].decode('unicode-escape')

			self.raws[-1]['summary'] = row['summary']				#  Unicode-escaped
			if self.raws[-1]['summary'] is not None:
				self.raws[-1]['summary'] = self.raws[-1]['summary'].decode('unicode-escape')

			self.raws[-1]['keyword'] = row['keyword']				#  Unicode-escaped
			if self.raws[-1]['keyword'] is not None:
				self.raws[-1]['keyword'] = self.raws[-1]['keyword'].decode('unicode-escape')

			self.raws[-1]['lang-claimed'] = row['lang_claimed']		#  Unicode-escaped

			self.raws[-1]['lang-detected'] = row['lang_detected']	#  ASCII string
			self.raws[-1]['pub-date'] = row['pub_date']				#  Datetime
			self.raws[-1]['date-retrieved'] = row['ret_date']		#  Datetime
		if self.useConfidence and self.verbose:
			print('Pulled ' + str(len(self.raws)) + ' unprocessed records with confidence >= ' + str(self.confidence))
		elif self.verbose:
			print('Pulled ' + str(len(self.raws)) + ' unprocessed records.')

		cursor.close()
		return

	#  A more specific record-retrieval routine:
	#  If 'k' is a list, then fetch all articles corresponding to each KP in 'k' and store them in 'raws'.
	#  If 'k' is an int, then fetch the article with KP 'k' and store it in 'raws'.
	def select(self, k):
		#  Declare dictionary-type cursor (assoc-arrays)
		cursor = self.link.cursor(MySQLdb.cursors.DictCursor)

		if isinstance(k, list):
			for kp in k:
				query  = 'SELECT * FROM articles WHERE kp = ' + str(kp) + ';'
				cursor.execute(query)
				result = cursor.fetchall()
				for row in result:
					self.raws.append( {} )
					self.raws[-1]['kp'] = int(row['kp'])					#  Int
					self.raws[-1]['url'] = row['url']						#  ASCII string

					self.raws[-1]['title'] = row['title']					#  Unicode-escaped
					if self.raws[-1]['title'] is not None:
						self.raws[-1]['title'] = self.raws[-1]['title'].decode('unicode-escape')

					self.raws[-1]['text'] = row['content']					#  Unicode-escaped
					if self.raws[-1]['text'] is not None:
						self.raws[-1]['text'] = self.raws[-1]['text'].decode('unicode-escape')

					self.raws[-1]['summary'] = row['summary']				#  Unicode-escaped
					if self.raws[-1]['summary'] is not None:
						self.raws[-1]['summary'] = self.raws[-1]['summary'].decode('unicode-escape')

					self.raws[-1]['keyword'] = row['keyword']				#  Unicode-escaped
					if self.raws[-1]['keyword'] is not None:
						self.raws[-1]['keyword'] = self.raws[-1]['keyword'].decode('unicode-escape')

					self.raws[-1]['lang-claimed'] = row['lang_claimed']		#  Unicode-escaped

					self.raws[-1]['lang-detected'] = row['lang_detected']	#  ASCII string
					self.raws[-1]['pub-date'] = row['pub_date']				#  Datetime
					self.raws[-1]['date-retrieved'] = row['ret_date']		#  Datetime

		elif isinstance(k, int):
			query  = 'SELECT * FROM articles WHERE kp = ' + str(k) + ';'
			cursor.execute(query)
			result = cursor.fetchall()
			for row in result:
				self.raws.append( {} )
				self.raws[-1]['kp'] = int(row['kp'])						#  Int
				self.raws[-1]['url'] = row['url']							#  ASCII string

				self.raws[-1]['title'] = row['title']						#  Unicode-escaped
				if self.raws[-1]['title'] is not None:
					self.raws[-1]['title'] = self.raws[-1]['title'].decode('unicode-escape')

				self.raws[-1]['text'] = row['content']						#  Unicode-escaped
				if self.raws[-1]['text'] is not None:
					self.raws[-1]['text'] = self.raws[-1]['text'].decode('unicode-escape')

				self.raws[-1]['summary'] = row['summary']					#  Unicode-escaped
				if self.raws[-1]['summary'] is not None:
					self.raws[-1]['summary'] = self.raws[-1]['summary'].decode('unicode-escape')

				self.raws[-1]['keyword'] = row['keyword']					#  Unicode-escaped
				if self.raws[-1]['keyword'] is not None:
					self.raws[-1]['keyword'] = self.raws[-1]['keyword'].decode('unicode-escape')

				self.raws[-1]['lang-claimed'] = row['lang_claimed']			#  Unicode-escaped

				self.raws[-1]['lang-detected'] = row['lang_detected']		#  ASCII string
				self.raws[-1]['pub-date'] = row['pub_date']					#  Datetime
				self.raws[-1]['date-retrieved'] = row['ret_date']			#  Datetime

		cursor.close()
		return

	#  A more specific record-cleaning routine:
	#  Assumes 'raws' has the expected content.
	#  Builds a bag of words for the raw record [i] using language 'lang'
	def clean(self, lang, i):
		bow = []						#  Fresh for each article
		targets = []					#  Remember constant assumption that records are incomplete
		if self.raws[i]['title'] is not None:
			targets.append(self.raws[i]['title'])
		if self.raws[i]['text'] is not None:
			targets.append(self.raws[i]['text'])
		if self.raws[i]['summary'] is not None:
			targets.append(self.raws[i]['summary'])
		if self.raws[i]['keyword'] is not None:
			targets.append(self.raws[i]['keyword'])

		for target in targets:
			if self.verbose:
				print('Cleaning ' + target)
			bow += [x for x in self.process(lang, target, self.segmenter)]

		self.bags.append(bow)

		return

	#  Assumes raws[] and bags[] have content
	#  Online saves do NOT update the timing table
	def save(self):
		if self.link is not None:	#  Attempt to save to the DB
			cursor = self.link.cursor(MySQLdb.cursors.DictCursor)

			if self.verbose:
				print("\n")
				sys.stdout.write('Updating database: 0%' + "\r")
				sys.stdout.flush()

			for i in range(0, len(self.raws)):
									#  Convert Unicode strings to DB-safe representations
									#  u'montclair'          ==> 'montclair'
									#  u'\u4f0a\u6717\u4eba' ==> '\u4f0a\u6717\u4eba'
				safe = [repr(x)[2:-1] for x in self.bags[i]]
				safe = [re.sub(r'\"', '\\\"', x) for x in safe]
				safe = [re.sub(r'\u', '\\u', x) for x in safe]

				query  = 'UPDATE articles SET'
				query += ' bag_of_words = "' + "\t".join(safe) + '",'
				query += ' processed = TRUE'
				query += ' WHERE kp = ' + str(self.raws[i]['kp']) + ';'
				cursor.execute(query)
				self.link.commit()

				if self.verbose:
					sys.stdout.write('Updating database: ' + \
					                 str(int(float(i + 1) / float(len(self.raws)) * 100)) + '%' + "\r")
					sys.stdout.flush()

			if self.verbose:
				print("\n")

			cursor.close()
		elif self.verbose:
			print('No database connection; unable to save.')
		return

	#  Create a new DB entry for the cleaning process we are about to begin.
	#  This way, if something goes wrong, we can pick up where we left off
	def declareProc(self):
		#  Declare dictionary-type cursor (assoc-arrays)
		cursor = self.link.cursor(MySQLdb.cursors.DictCursor)

		query  = 'INSERT INTO baggings(date_started)'
		query += ' VALUES("' + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '");'
		cursor.execute(query)
		self.link.commit()

		self.procId = cursor.lastrowid
		if self.verbose:
			print('Created cleaning process #' + str(self.procId))

		cursor.close()
		return

	#  Help our Chinese segmenter by first identifying substrings of Western characters.
	#  We define "Western" generally as any character with a numerical equivalent in range
	#  [0, 255]. This will catch everything in the ASCII character set, but we must test
	#  further, case by case, for Western characters which are outside the ASCII set.
	#  What about Cyrillic, Turkish, Polish, Swedish, etc?
	def isWestern(self, ch):
		#  From NULL to lower-case y with diaeresis
		if ord(ch) >= 0 and ord(ch) <= 255:
			return True
		#  From upper-case A with macron, to lower-case y with macron
		if ord(ch) >= 256 and ord(ch) <= 563:
			return True
		#  Not sure if these symbols occur in any language or whether they are typically used
		#  in equations and formulas.
		#  From lower-case l with curl, to lower-case modifier y
		if ord(ch) >= 564 and ord(ch) <= 696:
			return True
		#  From Greek upper-case Heta, to Greek upper-case reversed dotted lunate Sigma
		if ord(ch) >= 880 and ord(ch) <= 1023:
			return True
		#  From Cyrillic upper-case E grave, to Cyrillic lower-case el with descender
		if ord(ch) >= 1024 and ord(ch) <= 1327:
			return True
		#  From Armenian upper-case Ayb, to Armenian upper-case Feh
		if ord(ch) >= 1329 and ord(ch) <= 1366:
			return True
		#  From Armenian modifier left-half ring, to Armenian abbreviation mark
		if ord(ch) >= 1369 and ord(ch) <= 1375:
			return True
		#  From Armenian lower-case ayb, to Armenian lower-case ligature ech-yiwn
		if ord(ch) >= 1377 and ord(ch) <= 1415:
			return True

		return False

	#  18JAN18: StanfordSegmenter quarantined until we can build an English dataset
	def initSegmenter(self):
		self.segmenter = StanfordSegmenter(java_class='edu.stanford.nlp.ie.crf.CRFClassifier', \
		  path_to_jar='/var/www/html/aggregator/stanford-segmenter-2017-06-09/stanford-segmenter-3.8.0.jar', \
		  path_to_sihan_corpora_dict='/var/www/html/aggregator/stanford-segmenter-2017-06-09/data', \
		  path_to_model='/var/www/html/aggregator/stanford-segmenter-2017-06-09/data/pku.gz', \
		  path_to_dict='/var/www/html/aggregator/stanford-segmenter-2017-06-09/data/dict-chris6.ser.gz')

		return

	#  If they were not provided in the constructor, they may be provided here.
	def setDBcredentials(self, host, uname, pword, table):
		self.dbHost = host
		self.dbUname = uname
		self.dbPword = pword
		self.dbTable = table
		return

	#  Attempt to open a connection to the database using the DB attributes
	def openDB(self):
		if self.dbHost is not None and \
		   self.dbUser is not None and \
		   self.dbPword is not None and \
		   self.dbTable is not None:
			self.link = MySQLdb.connect(self.dbHost, self.dbUser, self.dbPword, self.dbTable)
		elif self.verbose:
			print('Unable to open a DB connection because credentials are missing.')

		return

	#  Close the connection to the database
	def closeDB(self):
		self.link.close()
		return

	def setLimit(self, x):
		if x > 0:
			self.limit = x
		return

	def setLanguage(self, langStr):
		if langStr != '*':
			self.languageFilter = langStr
		else:
			self.languageFilter = None
		return

	def startTimer(self):
		self.startTime = time.mktime(time.gmtime())
		return

	def stopTimer(self):
		self.stopTime = time.mktime(time.gmtime())
		return
