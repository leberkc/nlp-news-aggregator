# -*- coding: utf-8 -*-
import time							#  Track how long things take
import sys							#  Used for re-writable screen output
import re							#  For find-and-replace work
import math
import MySQLdb						#  Used for DB operations
from datetime import datetime		#  Used for time stamping our retrievals
									#  Used for English only to get (e.g.) "catch" from "caught",
from nltk.stem.wordnet import WordNetLemmatizer							#  "bring" from "brought"
import gensim						#  Topic-modeling engine
from gensim import corpora

from corpusbuilder import CorpusBuilder

class Keyworder:
	#  kw = Keyworder('localhost', 'censor', 'blockme', 'corpora')
	def __init__(self, dbHost=None, dbUser=None, dbPword=None, dbTable=None):
		#  Discovering keywords happens relative to a given set of documents

		self.link = None			#  MySQL link
		self.dbHost = dbHost		#  String indicating database host
		self.dbUser = dbUser		#  String indicating database user
		self.dbPword = dbPword		#  String indicating database password
		self.dbTable = dbTable		#  String indicating database table

		self.startTime = None		#  Time this routine
		self.stopTime = None

		self.verbose = False		#  Whether to print progress to screen

	#  Perform Latent Dirichlet Allocation on the assumptions that...
	#  'topics' number of topics exist,
	#  'words' number of words make up a topic
	#  and refine our model with 'passes' number of passes.
	def lda(self, corpus, topics, words, passes):
		if self.verbose:
			print('Performing LDA:')
			print("\t" + str(topics) + ' topics')
			print("\t" + str(words) + ' words per topic')
			print("\t" + str(passes) + ' passes')

		ldamodel = gensim.models.ldamodel.LdaModel(doc_term_matrix, num_topics=topics, id2word=dictionary, passes=passes)
		result = ldamodel.print_topics(num_topics=topics, num_words=words)

		if self.verbose:
			print('LDA complete.')
		return

	#  Several flavors of TF-IDF:
	#  https://en.wikipedia.org/wiki/Tf%E2%80%93idf
	#  NMF
	#  https://en.wikipedia.org/wiki/Non-negative_matrix_factorization

	#  Term Frequency
	def tf(word, document):
		return freq(word, document) / float(wordCount(document))

	#  Inverse Document Frequency
	def idf(word, docList):
		return math.log(len(docList) / float(numDocsContaining(word, docList)))

	#  Term Frequency-Inverse Document Frequency
	def tfidf(word, document, docList):
		return tf(word, document) * idf(word, docList)

	#  Total appearances of WORD in single DOCUMENT
	def freq(word, document):
		return document.count(word)

	#  Total words in DOCUMENT
	def wordCount(document):
		return len(document)

	#  Number of documents in DOCLIST containing at least on appearance of WORD
	def numDocsContaining(word, docList):
		count = 0
		for doc in docList:
			if freq(word, doc) > 0:
				count += 1
		return count

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
