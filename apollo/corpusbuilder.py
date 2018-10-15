import MySQLdb						#  Used for DB operations

'''
A corpus is understood to be a list of strings, where each string represents a "document":
  ["Lorem ipsum dolor sit amet...",
   "Lorem ipsum dolor sit amet...",
   ... ]

Whether that document came from an article, a Weibo scraping, a blog post, or whatever, its participation
in our analytical engine begins as a long string in a list. When a system user wants clusters or topics, then,
these things are computed relative to some corpus which is a subset of the contents in our repository, possibly
including the entire repository. This CorpusBuilder class, then, is the collection and organization tool. It
facilitates requests like, "Build me a corpus of articles #1 through #5678" by returning a list of 5678 strings.

Going forward, expect this class to contain a dictionary object for every "type" we store in our repository.
self.articles will contain retrievals from the 'articles' table.
self.weibo will contain retrievals from the 'weibo' table.
  etc.
So this will change as we add resources and the accompanying resource-collection routines.
'''

#  Example use:
#  from corpusbuilder import CorpusBuilder
#  cb = CorpusBuilder('localhost', 'censor', 'blockme', 'corpora')
#  cb.openDB()
#  cb.addArticleK(1234)
#  cb.addArticleK(1235)
#  cb.addArticleK(1236)
#  cb.addArticleK(1237)
#  cb.fetchArticles()
#  cb.closeDB()
#  c = cb.bags()

class CorpusBuilder:
	#  cb = CorpusBuilder('localhost', 'censor', 'blockme', 'corpora')
	def __init__(self, dbHost=None, dbUser=None, dbPword=None, dbTable=None):
		#  Discovering keywords happens relative to a given set of documents
		self.articles = {}			#  [kp] ==> { ['lang'] ==> "en"
									#             ['title'] ==> "Lorem ipsum dolor sit amet"
									#             ['content'] ==> "Lorem ipsum dolor sit amet"
									#             ['summary'] ==> "Lorem ipsum dolor sit amet"
									#             ['keyword'] ==> "Lorem ipsum dolor sit amet"
									#             ['bag_of_words'] ==> "lorem,ipsum,dolor,sit,amet"
									#           }
		self.weibo = {}				#  T.B.D.
		self.freeweibo = {}			#  [kp] ==> { ['lang'] ==> "zh"
									#             ['content'] ==> "Lorem ipsum dolor sit amet"
									#             ['data-id'] ==> "1234"
									#             ['weibo-id'] ==> "5678"
									#             ['pub-date'] ==> ""
									#             ['date-retrieved'] ==> ""
									#           }

		self.link = None			#  MySQL link
		self.dbHost = dbHost		#  String indicating database host
		self.dbUser = dbUser		#  String indicating database user
		self.dbPword = dbPword		#  String indicating database password
		self.dbTable = dbTable		#  String indicating database table

		self.startTime = None		#  Time this routine
		self.stopTime = None

		self.verbose = False		#  Whether to print progress to screen

	#  What you came to corpusbuilder.py for:
	#  Return a (probably massive) dictionary of TAB-SEPARATED strings, one for every source identified.
	#  Keys are formatted to identify the source: <table-name>-<record KP>
	#  For instance:
	#    bows[articles-1234] = "great \t big \t bag \t of \t words \t for \t article \t number \t 1234"
	#    bows[articles-1235] = "great \t big \t bag \t of \t words \t for \t article \t number \t 1235"
	#     ...
	#    bows[weibo-1234] = "great \t big \t bag \t of \t words \t for \t weibo \t post \t number \t 1234"
	def bags(self):
		bows = {}
		for k, v in self.articles.items():
			bows['articles-' + str(k)] = v['bag_of_words']
		for k, v in self.weibo.items():
			bows['weibo-' + str(k)] = v['bag_of_words']
		for k, v in self.freeweibo.items():
			bows['freeweibo-' + str(k)] = v['bag_of_words']
		return bows

	### A R T I C L E S ###########################################################################
	#  Add the article KP 'i' to 'articles' for computing clusters, keywords, topics, etc.
	#  cb.addArticleK( [x for x in range(9661, 9688)] )
	def addArticleK(self, i):
		if isinstance(i, list):
			for ii in i:
				if ii not in self.articles.keys():
					self.articles[ii] = {}
		elif i not in self.articles.keys():
			self.articles[i] = {}
		return

	#  Remove the article KP 'i' from 'articles' for computing clusters, keywords, topics, etc.
	def rmArticleK(self, i):
		if isinstance(i, list):
			for ii in i:
				if ii in self.articles.keys():
					del self.articles[ii]
		elif i in self.articles.keys():
			del self.articles[i]
		return

	#  Return a list of KPs for all articles in language identified by 'lang',
	#  whether claimed or detected.
	#  For example, get all English: cb.lookupLanguage('en')
	#               get all Chinese: cb.lookupLanguage('zh')
	def lookupLanguage(self, lang):
		keys = []
		if self.link is not None:
			cursor = self.link.cursor(MySQLdb.cursors.DictCursor)
			query  = 'SELECT kp FROM articles WHERE'
			query += ' (lang_claimed = "' + lang + '" OR lang_detected = "' + lang + '")'
			query += ' AND bag_of_words IS NOT NULL;'
			cursor.execute(query)
			result = cursor.fetchall()
			for row in result:
				keys.append(int(row['kp']))
			cursor.close()
		return keys

	#  Reset self.articles to an empty dictionary
	def purgeArticles(self):
		self.articles = {}
		return

	#  Fetch values for whichever keys have been added to self.articles
	def fetchArticles(self):
		if self.link is not None:
			cursor = self.link.cursor(MySQLdb.cursors.DictCursor)
			for k in self.articles.keys():
				if self.verbose:
					print('Retrieving articles[' + str(k) + ']')

				query  = 'SELECT title, content, summary, keyword, bag_of_words FROM articles WHERE kp = ' + str(k) + ';'
				cursor.execute(query)
				result = cursor.fetchall()
				for row in result:											#  Expect text is Unicode-escaped
					self.articles[k]['title'] = row['title']
					if self.articles[k]['title'] is not None:
						self.articles[k]['title'] = self.articles[k]['title'].decode('unicode-escape')

					self.articles[k]['content'] = row['content']
					if self.articles[k]['content'] is not None:
						self.articles[k]['content'] = self.articles[k]['content'].decode('unicode-escape')

					self.articles[k]['summary'] = row['summary']
					if self.articles[k]['summary'] is not None:
						self.articles[k]['summary'] = self.articles[k]['summary'].decode('unicode-escape')

					self.articles[k]['keyword'] = row['keyword']
					if self.articles[k]['keyword'] is not None:
						self.articles[k]['keyword'] = self.articles[k]['keyword'].decode('unicode-escape')

					self.articles[k]['bag_of_words'] = row['bag_of_words']
					if self.articles[k]['bag_of_words'] is not None:
						self.articles[k]['bag_of_words'] = self.articles[k]['bag_of_words'].decode('unicode-escape')

			cursor.close()

		elif self.verbose:
			print("Unable to pull articles because not connected to database.")

		return

	### W E I B O #################################################################################
	#  Add the Weibo post KP 'i' to 'weibo' for computing clusters, keywords, topics, etc.
	def addWeiboK(self, i):
		if isinstance(i, list):
			for ii in i:
				if ii not in self.weibo.keys():
					self.weibo[ii] = {}
		elif i not in self.weibo.keys():
			self.weibo[i] = {}
		return

	#  Remove the Weibo post KP 'i' from 'weibo' for computing clusters, keywords, topics, etc.
	def rmWeiboK(self, i):
		if isinstance(i, list):
			for ii in i:
				if ii in self.weibo.keys():
					del self.weibo[ii]
		elif i in self.weibo.keys():
			del self.weibo[i]
		return

	#  Reset self.weibo to an empty dictionary
	def purgeWeibo(self):
		self.weibo = {}
		return

	#  Fetch values for whichever keys have been added to self.weibo
	def fetchWeibo(self):
		if self.link is not None:
			cursor = self.link.cursor(MySQLdb.cursors.DictCursor)
			for k in self.weibo.keys():
				if self.verbose:
					print('Retrieving Weibo post[' + str(k) + ']')

				query  = 'SELECT title, content, summary, keyword, bag_of_words FROM weibo WHERE kp = ' + str(k) + ';'
				cursor.execute(query)
				result = cursor.fetchall()
				for row in result:											#  Expect text is Unicode-escaped
					self.weibo[k]['title'] = row['title']
					if self.weibo[k]['title'] is not None:
						self.weibo[k]['title'] = self.weibo[k]['title'].decode('unicode-escape')

					self.weibo[k]['content'] = row['content']
					if self.weibo[k]['content'] is not None:
						self.weibo[k]['content'] = self.weibo[k]['content'].decode('unicode-escape')

					self.weibo[k]['summary'] = row['summary']
					if self.weibo[k]['summary'] is not None:
						self.weibo[k]['summary'] = self.weibo[k]['summary'].decode('unicode-escape')

					self.weibo[k]['keyword'] = row['keyword']
					if self.weibo[k]['keyword'] is not None:
						self.weibo[k]['keyword'] = self.weibo[k]['keyword'].decode('unicode-escape')

					self.weibo[k]['bag_of_words'] = row['bag_of_words']
					if self.weibo[k]['bag_of_words'] is not None:
						self.weibo[k]['bag_of_words'] = self.weibo[k]['bag_of_words'].decode('unicode-escape')

			cursor.close()

		elif self.verbose:
			print("Unable to pull weibo posts because not connected to database.")

		return

	### F R E E W E I B O #########################################################################
	#  Add the FreeWeibo post KP 'i' to 'freeweibo' for computing clusters, keywords, topics, etc.
	def addFreeWeiboK(self, i):
		if isinstance(i, list):
			for ii in i:
				if ii not in self.freeweibo.keys():
					self.freeweibo[ii] = {}
		elif i not in self.freeweibo.keys():
			self.freeweibo[i] = {}
		return

	#  Remove the FreeWeibo post KP 'i' from 'freeweibo' for computing clusters, keywords, topics, etc.
	def rmFreeWeiboK(self, i):
		if isinstance(i, list):
			for ii in i:
				if ii in self.freeweibo.keys():
					del self.freeweibo[ii]
		elif i in self.freeweibo.keys():
			del self.freeweibo[i]
		return

	#  Reset self.freeweibo to an empty dictionary
	def purgeFreeWeibo(self, i):
		self.freeweibo = {}
		return

	#  Fetch values for whichever keys have been added to self.freeweibo
	def fetchFreeWeibo(self, i):
		if self.link is not None:
			cursor = self.link.cursor(MySQLdb.cursors.DictCursor)
			for k in self.freeweibo.keys():
				if self.verbose:
					print('Retrieving FreeWeibo post[' + str(k) + ']')

				query  = 'SELECT content, data_id, weibo_id, pub_date, date_retrieved, bag_of_words FROM freeweibo WHERE kp = ' + str(k) + ';'
				cursor.execute(query)
				result = cursor.fetchall()
				for row in result:											#  Expect text is Unicode-escaped
					self.freeweibo[k]['content'] = row['content']
					if self.freeweibo[k]['content'] is not None:
						self.freeweibo[k]['content'] = self.freeweibo[k]['content'].decode('unicode-escape')

					self.freeweibo[k]['data_id'] = row['data_id']

					self.freeweibo[k]['weibo_id'] = row['weibo_id']

					self.freeweibo[k]['pub_date'] = row['pub_date']

					self.freeweibo[k]['date_retrieved'] = row['date_retrieved']

					self.freeweibo[k]['bag_of_words'] = row['bag_of_words']
					if self.freeweibo[k]['bag_of_words'] is not None:
						self.freeweibo[k]['bag_of_words'] = self.freeweibo[k]['bag_of_words'].decode('unicode-escape')

			cursor.close()

		elif self.verbose:
			print("Unable to pull freeweibo posts because not connected to database.")

		return

	### D B   S t u f f ###########################################################################
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

	def startTimer(self):
		self.startTime = time.mktime(time.gmtime())
		return

	def stopTimer(self):
		self.stopTime = time.mktime(time.gmtime())
		return
