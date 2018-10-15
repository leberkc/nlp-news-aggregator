#  This is the class that models our hypothetical COLLECTIVE ACTION POTENTIAL.
#  As other experiments should do, the Apollo class makes primary use of
#  CorpusBuilder and CorpusAnalyst to collect documents and perform the
#  rudimentary processing.

import MySQLdb						#  Used for DB operations
import time							#  Track how long things take
import sys							#  Used for re-writable screen output
from datetime import datetime		#  Used for time stamping our performance metrics
from corpusbuilder import CorpusBuilder
from corpusanalyst import CorpusAnalyst

class Apollo:
	def __init__(self):
		self.link = None			#  MySQL link
		self.dbHost = None			#  String indicating database host
		self.dbUser = None			#  String indicating database user
		self.dbPword = None			#  String indicating database password
		self.dbTable = None			#  String indicating database table

		self.startTime = None		#  Time routines
		self.stopTime = None

		self.verbose = False

		return

	def collectiveActionPotential(self, numClusters, cosineThreshold):

		self.startTimer()			#  Time the computation of this heuristic

		#  Build a Builder to fetch things for us
		cb = CorpusBuilder('localhost', 'censor', 'blockme', 'corpora')
		cb.openDB()
		cb.addArticleK(cb.lookupLanguage('en'))
		cb.fetchArticles()
		cb.closeDB()
		c = cb.bags()

		#  Build an Analyst to process documents for us
		ca = CorpusAnalyst(c)
		ca.verbose = True
		ca.setLang('en')
		ca.pullPunct()				#  Clear out punctuation
		ca.initWordNetLemma()		#  Set Lemmatizer to WordNet
		ca.lemmatizeCorpus()		#  Lemmatize corpus
		ca.pullStopwords()			#  Remove stopwords
		ca.pullNumeric()			#  Remove numbers
									#  Remove unwanted words
		ca.pullWords(['reuters', 'say', "'s", 'said', 'mr', 'ha', 'wa'])

		td = ca.tfidf_file()		#  Compute Tf-Idf and save to file
									#  Compute 'numClusters' clusters, each with 15 top words
		clusters = ca.kmeans(numClusters, 15, td)

		if self.verbose:
			print("")
			sys.stdout.write('Averaging cluster Alexa ranks: 0%' + "\r")
			sys.stdout.flush()
									#  Connect to DB ourselves
		self.setDBcredentials('localhost', 'censor', 'blockme', 'corpora')
		self.openDB()

		avgRanks = {}				#  Prepare to collect Alexa ranks:
									#  [key] = cluster number; [val] = average Alexa rank for cluster
		total = 0
									#  Each in clusters is tuple of two lists: documents, top terms
		for c in range(0, len(clusters)):
			avgRanks[c] = 0.0
			foundCtr = 0
			total += len(clusters[c][0])
			for doc in clusters[c][0]:
				r = self.getSourceAlexaRank(doc)
				if r is not None:
					avgRanks[c] += float(r)
					foundCtr += 1
			avgRanks[c] /= float(foundCtr)

			if self.verbose:
				sys.stdout.write('Averaging cluster Alexa ranks: ' + \
						         str(int(float(c) / float(len(clusters) - 1) * 100)) + '%' + "\r")
				sys.stdout.flush()

		if self.verbose:
			print('')

									#  Write clusters to file with Alexa ranks
		if self.verbose:
			print("")
			sys.stdout.write('Writing ' + str(len(clusters)) + ' clusters to file: 0%' + "\r")
			sys.stdout.flush()

		fh = open('clusters.' + str(ca.id) + '.txt', 'w')
		#  Write file header
		fstr = 'K-Means: ' + str(total) + ' documents, ' + str(len(clusters)) + ' clusters' + '\n'
		fh.write(fstr)
		fh.write('-' * len(fstr) + '\n')
		for c in range(0, len(clusters)):

			#  Write cluster header
			fh.write('CLUSTER #' + str(c) + ': ' + str(len(clusters[c][0])) + ' documents' + '\n')
			fh.write('\tAverage Alexa rank: ' + str(avgRanks[c]) + '\n')
			fstr = '\tTop ' + str(len(clusters[c][1])) + ' words:' + '\n\t\t'
			for word in clusters[c][1]:
				if isinstance(word, unicode):
					fstr += repr(word).encode('ascii')[2:-1] + ', '
				else:
					fstr += word + ', '
			fstr = fstr[:-2] + '\n\n'
			fh.write(fstr)

			#  Write cluster documents
			for doc in clusters[c][0]:
				fh.write('\t' + doc + '\n')

			fh.write('\n')

			if self.verbose:
				sys.stdout.write('Writing ' + str(len(clusters)) + ' clusters to file: ' + \
					             str(int(float(c) / float(len(clusters) - 1) * 100)) + '%' + "\r")
				sys.stdout.flush()

		fh.close()

		if self.verbose:
			print('')
									#  Write Cosine-Similarity to file
		ca.cossim_file(cosineThreshold, td)

		self.stopTimer()			#  Work is done: report how long it took
		cursor = self.link.cursor(MySQLdb.cursors.DictCursor)
		query  = 'INSERT INTO performance_metrics(process, parameter, date_started, sec)'
		query += ' VALUES("collective-action-potential", ' + str(total) + ', "'
		query +=          datetime.fromtimestamp(int(self.startTime)).strftime('%Y-%m-%d %H:%M:%S') + '", '
		query +=          str(self.stopTime - self.startTime) + ');'
		cursor.execute(query)
		self.link.commit()

		self.closeDB()				#  Close DB; we're done

		return

	#  Receives a string like 'articles-25667', looks up that document's source,
	#  and returns the source's MOST RECENT Alexa ranking!
	def getSourceAlexaRank(self, srcstr):

		rank = None

		if self.link is not None:

			arr = srcstr.split('-')
			cursor = self.link.cursor(MySQLdb.cursors.DictCursor)

			#  Fetch an article source
			if arr[0] == 'articles':
				query = 'SELECT source FROM article_source WHERE article_id = ' + arr[1] + ';'
				cursor.execute(query)
				result = cursor.fetchall()
				#  SHOULD only be one!
				for row in result:
					url = row['source']
					#  Remove "http://" and "https://"
					if 'http://' in url:
						url = url.replace("http://", "")
					if 'https://' in url:
						url = url.replace("https://", "")
					parse = url.split('/')
					#  Remove "www."
					if parse[0][0:4] == 'www.':
						url = parse[0][4:]
					else:
						url = parse[0][:]
				#  Now fetch all samplings from this source
				#  (we're only going to take the most recent)
				query = 'SELECT sampled, rank FROM alexa_rank WHERE src = "' + url + '";'
				cursor.execute(query)
				result = cursor.fetchall()
				latest = 0
				for row in result:
					if int(row['sampled']) > latest:
						latest = int(row['sampled'])
						rank = int(row['rank'])

			#  Handle FreeWeibo
			elif arr[0] == 'freeweibo':
				rank = None

			#  Handle Weibo
			elif arr[0] == 'weibo':
				rank = None

		elif self.verbose:
			print('Unable to perform query. You are not connected to the DB.')
			print('First call Apollo.setDBcredentials(host, username, password, table)')
			print('or Apollo.openDB()')

		return rank

	################################ D B   C o n n e c t i o n ####################################
	#  This class does not accept DB credentials in the constructor. It is mostly an offline tool,
	#  so does not assume that we want to connect to the DB right away.
	def setDBcredentials(self, host, uname, pword, table):
		self.dbHost = host
		self.dbUser = uname
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

	#################################### T i m e r ######################################
	#  May be informative to time routines
	def startTimer(self):
		self.startTime = time.mktime(time.gmtime())
		return

	def stopTimer(self):
		self.stopTime = time.mktime(time.gmtime())
		return
