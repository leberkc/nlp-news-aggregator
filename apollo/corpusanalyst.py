from __future__ import print_function
import re
import os
import sys
import codecs
import itertools					#  Used to generate all matrix coordinate pairs
import uuid							#  Generate a UUID for each prospective corpus
import numpy as np					#  Python's advanced math library
import pandas as pd					#  Python's advanced data structures library
import nltk							#  Natural Language ToolKit
from nltk.corpus import stopwords	#  To remove statistically misleading words

									#  "Lemmatization" means, for example,
									#  getting "jump" from "jumped", "jumps", "jumping", ...
									#  getting "wolf" from "wolves"...
									#  getting "abacus" from "abaci"...
from nltk.stem.wordnet import WordNetLemmatizer
from nltk.stem.snowball import SnowballStemmer
import gensim						#  Used for LDA
from gensim import corpora			#  Used to build matrix indices for LDA engine
									#  SKLearn
from sklearn import feature_extraction
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import KMeans
from sklearn.externals import joblib

class CorpusAnalyst:
	#  ca = CorpusAnalyst()
	def __init__(self, docs=None):	#  If 'docs' is provided it is understood to be a dictionary
		self.documents = {}			#  where keys are document identifier strings
		if docs is not None:		#    (articles-1234, articles-1235, ..., weibo-1234, ... )
			for k, v in docs.items():
				self.documents[k] = v.split("\t")
									#  and values are the corresponding bags-of-words
									#    ("bag \t of \t words \t for \t article \t 1234",
									#     "bag \t of \t words \t for \t article \t 1235", ...,
									#     "bag \t of \t words \t for \t weibo \t post \t 1234", ...)

		self.lang = "en"			#  English by default
		self.lemma = None			#  Optional WordNet Lemmatizer (English only)
									#  Optional Snowball Lemmatizer (Several languages, see below)

									#  List of strings signifying punctuation marks
		self.punctuation = self.loadPunctList()
		self.verbose = False		#  Whether to print information to screen
		self.id = uuid.uuid4().int	#  Generate a UUID for this object and its corpus
									#  (mainly used for output files)
		self.cacheColHeader = None	#  SciPy sparse matrices will not track row or column labels,
		self.cacheRowHeader = None	#  so these vars internally track the arrangement of labels.

		return

	#################################  T F - I D F  #####################################
	#  Defaults are as follows:
	#  max_df=1.0			This was previously set to 0.8, and the thinking was this:
	#                       a term with frequency greater than 80% of the documents probably
	#                       caries little meanining. HOWEVER, when applied to our data, 0.8
	#                       cut away far too many words! Test runs were coming away with only
	#                       10 words!
	#  min_df=0.0			Similarly, this had been set to 0.2, requiring that a term be in
	#                       at least 20% of the documents. The thinking was that lower thresholds
	#                       may start to bias clustering toward same names, "Michael", "Tom", "Smith"...
	#                       These may occur frequently in a given document without necessarily
	#                       carrying meaning. Test runs, however, were being too severely cut.
	#  max_features=200000	Maximum number of features to discover
	#  use_idf=True			If False, computes term-frequency only
	#  ngram_range=(1, 1)	Consider unigrams only. (1, 2) would consider unigrams and bigrams.
	#                       (1, 3): uni-, bi-, trigrams, etc

	#  The "vanilla" version of this function just returns a term-document matrix (scipy.sparse.csr_matrix)
	def tfidf(self, max_df=1.0, min_df=0.0, max_features=200000, use_idf=True, ngram_range=(1, 1)):

		#  List of all document *TITLES*
		#  e.g. [articles-10999, articles-10998, articles-8806, articles-17696, ... ]
		self.cacheColHeader = self.allDocs()
		#  List of all document *WORDS*
		#  (each represented only once)
		#  e.g. [the, quick, brown, fox, jumped, over, lazy, dog... ]
		self.cacheRowHeader = self.allWords()

		if self.verbose:
			print('Running TF-IDF...')

		if self.verbose:
			print('\t' + str(len(self.cacheColHeader)) + ' documents')
			print('\t' + str(max_df) + ' maximum Doc.Freq.')
			print('\t' + str(min_df) + ' minimum Doc.Freq.')
			print('\t' + str(max_features) + ' maximum features')
			if use_idf:
				print('\tAlso computing IDF')
			else:
				print('\tNOT computing IDF')
			print('\tn-gram range: [' + str(ngram_range[0]) + ', ' + str(ngram_range[1]) + ']')

		#  The SKLearn kit gives us a bit more than we need, hence the lambda function below:
		#  by the time records are retrieved, they've already been tokenized into BoWs.
		#  (Users may or may not have removed stopwords and punctuation, though.)
		tfidf_vec = TfidfVectorizer(max_df=max_df, max_features=max_features, \
		                            tokenizer=lambda x: x.split(' '), stop_words='english', \
                                    min_df=min_df, use_idf=use_idf, ngram_range=ngram_range, \
                                    vocabulary=self.cacheRowHeader)

		#  This, too, is something of a workaround.
		#  The Vectorizer expects a list of strings, so we awkwardly oblige.
		docContent = []
		for title in self.cacheColHeader:
			docContent.append( ' '.join( self.documents[title] ) )

		#  [
		#    'all the text in document zero .',
		#    'all the text in document one .',
		#    'all the text in document two .',
		#    'all the text in document three .',
		#       ...
		#  ]
		tfidf_matrix = tfidf_vec.fit_transform(docContent)

		if self.verbose:
			#  Tuple: (documents, terms)
			print('TFIDF matrix shape: ' + str(tfidf_matrix.shape))

		return tfidf_matrix

	#  This version of TFIDF computes TFIDF or accepts an already-computed matrix and writes it to file.
	#  It also returns the Term-Document Matrix for pass-along purposes.
	def tfidf_file(self, M=None, max_df=1.0, min_df=0.0, max_features=200000, use_idf=True, ngram_range=(1, 1)):

		if M is None:
			#  Compute matrix
			tfidf_matrix = self.tfidf(max_df, min_df, max_features, use_idf, ngram_range)
		else:
			#  Use given matrix
			tfidf_matrix = M

		#  Write to SPARSE file:
		fh = open('tfidf.' + str(self.id) + '.sparse', 'w')

		#  Get coordinate tuples for all non-zero entries in sparse matrix
		Mx = tfidf_matrix.nonzero()
		#  zip() works here because of the way SciPy returns its answer for which
		#  indices contain non-zero values: (array([0, 0, 1, 2, 2]), array([0, 1, 2, 0, 2]))
		#  a tuple of arrays, where each 'i' in the first array is one coordinate (y)
		#  and each 'i' in the second array is the other coordinate (x)
		L = zip(Mx[0], Mx[1])

		ctr = 0
		total = len(L)

		if self.verbose:
			print("")
			sys.stdout.write('Writing sparse matrix to file: 0%' + "\r")
			sys.stdout.flush()

		#  Print table header
		if use_idf:
			fstr = 'Term\tDoc.\tTf-Idf'
		else:
			fstr = 'Term\tDoc.\tTf'
		fh.write(fstr + '\n')
		#  (Account for tab widths = 4 each, then minus 1)
		fh.write('-' * (len(fstr) + 6) + '\n')

		#  Print all non-zero elements
		for x in L:
			if isinstance(self.cacheRowHeader[x[1]], unicode):
				fh.write( repr(self.cacheRowHeader[x[1]]).encode('ascii')[2:-1] + '\t' + \
				          str(self.cacheColHeader[x[0]]) + '\t' + \
				          str(tfidf_matrix[x[0], x[1]]) + '\n')
			else:
				fh.write( str(self.cacheRowHeader[x[1]]) + '\t' + \
				          str(self.cacheColHeader[x[0]]) + '\t' + \
				          str(tfidf_matrix[x[0], x[1]]) + '\n')
			ctr += 1

			if self.verbose:
				sys.stdout.write('Writing sparse matrix to file: ' + \
					             str(int(float(ctr) / float(total) * 100)) + '%' + "\r")
				sys.stdout.flush()

		fh.close()

		if self.verbose:
			print('')

		return tfidf_matrix

	#  This version of TFIDF returns a term-document matrix (scipy.sparse.csr_matrix)
	#                        and a cosine-similarity matrix (scipy.sparse.csr_matrix).
	def tfidf_cossim(self, max_df=1.0, min_df=0.0, max_features=200000, use_idf=True, ngram_range=(1, 1)):

		tfidf_matrix = self.tfidf(max_df, min_df, max_features, use_idf, ngram_range)

		#  'dist' is 1 - the cosine similarity of each document.
		dist = 1 - cosine_similarity(tfidf_matrix)

		return tfidf_matrix, dist

	################################  C o s - S i m  ####################################
	#  Compute Cosine-Similarity
	#  (This either requires computing TfIdf first or using a ready-made Term-Document Matrix)
	def cossim(self, M=None, max_df=1.0, min_df=0.0, max_features=200000, use_idf=True, ngram_range=(1, 1)):
		if M is None:
			#  Compute matrix
			tfidf_matrix = self.tfidf(max_df, min_df, max_features, use_idf, ngram_range)
		else:
			#  Use given matrix
			tfidf_matrix = M

		#  'dist' is 1 - the cosine similarity of each document.
		dist = 1 - cosine_similarity(tfidf_matrix)

		return dist

	#  Write the Cosine-Similarity to file.
	#  If a Term-Document Matrix is provided, then use that one. Otherwise, compute your own.
	#  The only required argument, 'th', is the threshold,
	#  which we ONLY need when omitting weak associations from the written file.
	#  Returns the cosine-similarity matrix for pass-along purposes.
	def cossim_file(self, th=0.0, M=None, max_df=1.0, min_df=0.0, max_features=200000, use_idf=True, ngram_range=(1, 1)):
		if M is None:
			#  Compute matrix
			tfidf_matrix = self.tfidf(max_df, min_df, max_features, use_idf, ngram_range)
		else:
			#  Use given matrix
			tfidf_matrix = M

		#  'dist' is 1 - the cosine similarity of each document.
		dist = 1 - cosine_similarity(tfidf_matrix)

		ctr = 0
		total = len(self.cacheColHeader) * len(self.cacheColHeader)

		if self.verbose:
			print("")
			sys.stdout.write('Writing cosine similarities (threshold ' + str(th) + ') to file: 0%' + "\r")
			sys.stdout.flush()

		#  Remove 0. from the threshold and use it in the file name
		if th < 1.0:
			threshstr = re.sub(r'0\.', '', str(th))
		else:
			threshstr = '1'
		fh = open('cosine-' + threshstr + '.' + str(self.id) + '.edges', 'w')
		#  Print table header
		fstr = 'Cosine Similarities, threshold = ' + str(th)
		fh.write(fstr + '\n')
		fh.write('-' * len(fstr) + '\n')

		#  Print all edges above threshold
		for x in range(0, len(self.cacheColHeader)):
			for y in range(0, len(self.cacheColHeader)):
				if dist[x, y] >= th:
					fh.write( str(self.cacheColHeader[x]) + '\t' + \
					          str(self.cacheColHeader[y]) + '\t' + \
					          str(dist[x, y]) + '\n')
				ctr += 1

				if self.verbose:
					sys.stdout.write('Writing cosine similarities (threshold ' + str(th) + ') to file: ' + \
						             str(int(float(ctr) / float(total) * 100)) + '%' + "\r")
					sys.stdout.flush()

		fh.close()

		if self.verbose:
			print('')

		return dist

	#  This version of TFIDF computes TFIDF and Cosine-Similarity and writes each to file.
	#  This is a potentially time-consuming process for even modestly-sized corpora!
	#  Required input 'th' is Cosine-Similarity THRESHOLD:
	#  Beneath this threshold, do not record an edge to file
	def tfidf_cossim_file(self, th=0.0, max_df=1.0, min_df=0.0, max_features=200000, use_idf=True, ngram_range=(1, 1)):

		tfidf_matrix, dist = self.tfidf_cossim(max_df, min_df, max_features, use_idf, ngram_range)

		self.tfidf_file(tfidf_matrix, max_df, min_df, max_features, use_idf, ngram_range)

		self.cossim_file(th, tfidf_matrix, max_df, min_df, max_features, use_idf, ngram_range)

		return tfidf_matrix, dist

	################################  K - M e a n s  ####################################
	#  User must provide a number of topics for the algorithm to find.
	#  Return a dictionary of tuples:
	#  [cluster-number] ==> ( [source-string, source-string, ..., source-string],
	#                         [top, n, terms, for, cluster] )
	#  [cluster-number] ==> ( [source-string, source-string, ..., source-string],
	#                         [top, n, terms, for, cluster] )
	#   ...
	#  [cluster-number] ==> ( [source-string, source-string, ..., source-string],
	#                         [top, n, terms, for, cluster] )
	def kmeans(self, num_clusters, terms_per_cluster=10, M=None, max_df=1.0, min_df=0.0, max_features=200000, use_idf=True, ngram_range=(1, 1)):

		if M is None:
			#  Compute matrix
			M = self.tfidf(max_df, min_df, max_features, use_idf, ngram_range)

		if self.verbose:
			print("Computing K-Means, " + str(num_clusters) + " clusters...")

		#  Use the k-Means algorithm to discover document clusters
		km = KMeans(n_clusters=num_clusters)
		km.fit(M)
		clusters = km.labels_.tolist()

		if self.verbose:
			print("Done.")

		documents = { 'document': self.cacheColHeader, 'words': self.cacheRowHeader, 'cluster': clusters }
		frame = pd.DataFrame(documents, index=[clusters] , columns=['document', 'cluster'])
		order_centroids = km.cluster_centers_.argsort()[:, ::-1]

		topTerms = {}

		#  Display cluster information
		for i in range(num_clusters):

			topTerms[i] = []

			for ind in order_centroids[i, :terms_per_cluster]:
				topTerms[i].append(self.cacheRowHeader[ind])

		#  These zip up nicely.
		pairs = zip(clusters, self.cacheColHeader)
		#  Build a dictionary, keyed by cluster number, referring to a list of documents in this cluster
		cluDoc = {}
		for pair in pairs:
			if pair[0] not in cluDoc:
				cluDoc[ pair[0] ] = []
				cluDoc[ pair[0] ].append(pair[1])
			else:
				cluDoc[ pair[0] ].append(pair[1])

		#  BUild a dictionary, keyed by cluster number, reffering to a list of words germane to this cluster
		cluTerm = {}
		for c in range(0, num_clusters):
			cluTerm[c] = topTerms[c]

		#  Combine dictionaries: key is cluster number; value is tuple( [documents], [words] )
		clu = {}
		for c in range(0, num_clusters):
			clu[c] = (cluDoc[c], cluTerm[c])

		#  Result is organized by cluster
		return clu

	#  Write the results of K-Means to file
	def kmeans_file(self, num_clusters, terms_per_cluster=10, M=None, max_df=1.0, min_df=0.0, max_features=200000, use_idf=True, ngram_range=(1, 1)):
		clusters = self.kmeans(num_clusters, terms_per_cluster, M, max_df, min_df, max_features, use_idf, ngram_range)

		ctr = 0
		total = 0
		for k, v in clusters.items():
			total += len(v[0])

		#  Write to file:
		fh = open('kmeans.' + str(self.id) + '.txt', 'w')

		if self.verbose:
			print("")
			sys.stdout.write('Writing ' + str(num_clusters) + ' clusters to file: 0%' + "\r")
			sys.stdout.flush()

		#  Write file header
		fstr = 'K-Means: ' + str(total) + ' documents, ' + str(num_clusters) + ' clusters' + '\n'
		fh.write(fstr)
		fh.write('-' * len(fstr) + '\n')

		for k, v in sorted(clusters.items()):
			#  Write cluster header
			fh.write('CLUSTER #' + str(k) + ': ' + str(len(v[0])) + ' documents' + '\n')
			fstr = '\tTop ' + str(len(v[1])) + ' words:' + '\n\t\t'
			for vv in v[1]:
				if isinstance(vv, unicode):
					fstr += repr(vv).encode('ascii')[2:-1] + ', '
				else:
					fstr += vv + ', '
			fstr = fstr[:-2] + '\n\n'
			fh.write(fstr)

			for vv in v[0]:
				fh.write('\t' + vv + '\n')
				ctr += 1

			fh.write('\n')

			if self.verbose:
				sys.stdout.write('Writing ' + str(num_clusters) + ' clusters to file: ' + \
					             str(int(float(ctr) / float(total) * 100)) + '%' + "\r")
				sys.stdout.flush()

		fh.close()

		if self.verbose:
			print('')

		return clusters

	##################################### L D A #########################################

	##################################### N M F #########################################

	#################################### E d i t ########################################
	#  The following functions are those to be (optionally) used before any kind of
	#  corpus analysis is requested. These are mostly set-up, clean-up, and reference functions.

	#  Build a (long, flat) list of all document handles (titles, like articles-1234)
	def allDocs(self, docs=None):
		if docs is None:
			return self.documents.keys()
		return docs.keys()

	#  Build a (long, flat) list of all words in corpus, no redundancies
	def allWords(self, docs=None):
		if docs is None:
			docs = self.documents.values()

		#  Use a hash table for improved speed
		terms = {}

		total = 0
		ctr = 0

		if self.verbose:
			print("")
			sys.stdout.write('Assembling list of all types: 0%' + "\r")
			sys.stdout.flush()

			for doc in docs:
				total += len(doc)

		for doc in docs:			#  For every document
			for t in doc:			#  For every term in document
				if t not in terms:
					terms[t] = True
				ctr += 1
				if self.verbose:
					sys.stdout.write('Assembling list of all types: ' + \
					                 str(int(float(ctr) / float(total) * 100)) + '%' + "\r")
					sys.stdout.flush()

		if self.verbose:
			print("")

		return terms.keys()

	#  Use the internally-stored list 'punctuation' to scrub out all punctuation marks:
	#  we do not want punctuation emerging as words in a topic
	def pullPunct(self):
		docsCtr = 0
		docsTotal = len(self.documents.items())

		if self.verbose:
			print("")
			sys.stdout.write('Removing punctuation: 0%' + "\r")
			sys.stdout.flush()

		for k, v in self.documents.items():

			self.documents[k] = [x for x in v if x not in self.punctuation]
			docsCtr += 1

			if self.verbose:
				sys.stdout.write('Removing punctuation: ' + \
					             str(int(float(docsCtr) / float(docsTotal) * 100)) + '%' + "\r")
				sys.stdout.flush()

		if self.verbose:
			print("")

		return

	#  Some words that are not stopwords are nevertheless words we want to remove.
	#  "reuters", for instance, because it appeared in so many articles was being
	#  marked by LDA as a word germane to a topic. This function allows users to
	#  specify a string or list of strings that we should remove from the corpus.
	def pullWords(self, w):
		if isinstance(w, list):
			docsCtr = 0
			docsTotal = len(w)

			if self.verbose:
				wheader = 'Target words: '
				for word in w:
					wheader += word + ' '
				print(wheader + "\n")
				sys.stdout.write('Removing target words: 0%' + "\r")
				sys.stdout.flush()

			for word in w:			#  Remove all words in 'w' from all documents
				for k, v in self.documents.items():
					self.documents[k] = [x for x in v if x != word]
				docsCtr += 1
				if self.verbose:
					sys.stdout.write('Removing target words: ' + \
						             str(int(float(docsCtr) / float(docsTotal) * 100)) + '%' + "\r")
					sys.stdout.flush()

		elif isinstance(w, str):
			docsCtr = 0
			docsTotal = len(self.documents.items())

			if self.verbose:
				wheader = 'Target word: ' + w
				print(wheader + "\n")
				sys.stdout.write('Removing target word: 0%' + "\r")
				sys.stdout.flush()
									#  Remove single word 'w' from all documents
			for k, v in self.documents.items():
				self.documents[k] = [x for x in v if x != w]
				docsCtr += 1

				if self.verbose:
					sys.stdout.write('Removing target word: ' + \
						             str(int(float(docsCtr) / float(docsTotal) * 100)) + '%' + "\r")
					sys.stdout.flush()

		if self.verbose:
			print("")

		return

	#  Remove all numeric-only strings from all documents
	def pullNumeric(self):
		docsCtr = 0
		docsTotal = len(self.documents.items())

		if self.verbose:
			print("")
			sys.stdout.write('Removing numeric tokens: 0%' + "\r")
			sys.stdout.flush()

		for k, v in self.documents.items():

			self.documents[k] = [x for x in v if not x.isdigit()]
			docsCtr += 1

			if self.verbose:
				sys.stdout.write('Removing numeric tokens: ' + \
					             str(int(float(docsCtr) / float(docsTotal) * 100)) + '%' + "\r")
				sys.stdout.flush()

		if self.verbose:
			print("")

		return

	#  Abbreviations like U.S. are at risk of being treated as two single-letter words, "u" and "s".
	#  This function allows users to tell the corpus, "Find all members of list 'parts' and replace
	#  them with the single string 'whole'. The case mentioned would be repaired by calling
	#  ca.joinWords(["u", ".", "s", "."], "u.s.")
	#    or
	#  ca.joinWords(["u", "s"], "u.s.")
	#    if you've already pulled punctuation.
	def joinWords(self, parts, whole):
		if len(parts) == 0:			#  Guard against empty lists (they'll throw off our tests)
			return

		for k, v in self.documents.items():
			allPartsFound = True	#  Check whether this document contains ALL parts
			for part in parts:
				if part not in v:
					allPartsFound = False
					break
			if allPartsFound:		#  All parts were present in the document 'v'... but is it an
				partsCounts = []	#  even number of times? How might we know which "u"s and "s"es
				for part in parts:	#  belong to "u.s." and which belong to "u.s.s.r."?
					partsCounts.append(v.count(part))
									#  We can mitigate this uncertainty by only replacing as many
									#  complete sets of the parts as have been found with only
									#  as many instances of 'whole'.
				for i in range(0, min(partsCounts)):
					index = None	#  Word order may not matter, but we try to be helpful
									#  by inserting 'whole' at the first instance of 'part'
					for part in parts:
						if part in self.documents[k]:
							if index is None:
								index = self.documents[k].index(part)
							self.documents[k].remove(part)
				for i in range(0, min(partsCounts)):
					if index is None:
						index = 0	#  Fallback: add to the beginning
					self.documents[k].insert(index, whole)
		return

	#  Remove the stopwords from all documents in corpus:
	#  Unless otherwise specified with the optional parameter,
	#  the language is assumed to be the language of this object.
	def pullStopwords(self, stoplang=None):
		if stoplang is None:		#  Default assumption is that we are pulling stopwords in the
			stoplang = self.lang	#  language assigned to this object

		docsCtr = 0
		docsTotal = len(self.documents.items())

		if self.verbose:
			print("")
			sys.stdout.write('Pulling stopwords: 0%' + "\r")
			sys.stdout.flush()

		for k, v in self.documents.items():
			#  Arabic
			if stoplang == 'ar':
				self.documents[k] = [x for x in v if x not in stopwords.words('arabic')]
			#  Danish
			elif stoplang == 'da':
				self.documents[k] = [x for x in v if x not in stopwords.words('danish')]
			#  German
			elif stoplang == 'de':
				self.documents[k] = [x for x in v if x not in stopwords.words('german')]
			#  Spanish
			elif stoplang == 'es':
				self.documents[k] = [x for x in v if x not in stopwords.words('spanish')]
			#  Finnish
			elif stoplang == 'fi':
				self.documents[k] = [x for x in v if x not in stopwords.words('finnish')]
			#  French
			elif stoplang == 'fr':
				self.documents[k] = [x for x in v if x not in stopwords.words('french')]
			#  Hungarian
			elif stoplang == 'hu':
				self.documents[k] = [x for x in v if x not in stopwords.words('hungarian')]
			#  Italian
			elif stoplang == 'it':
				self.documents[k] = [x for x in v if x not in stopwords.words('italian')]
			#  Kazakh
			elif stoplang == 'kk':
				self.documents[k] = [x for x in v if x not in stopwords.words('kazakh')]
			#  Dutch
			elif stoplang == 'nl':
				self.documents[k] = [x for x in v if x not in stopwords.words('dutch')]
			#  Norwegian
			elif stoplang == 'no':
				self.documents[k] = [x for x in v if x not in stopwords.words('norwegian')]
			#  Portuguese (Brazilian and Portuguese)
			elif stoplang == 'pt_BR' or stoplang == 'pt_PT' or stoplang == 'pt':
				self.documents[k] = [x for x in v if x not in stopwords.words('portuguese')]
			#  Romanian
			elif stoplang == 'ro':
				self.documents[k] = [x for x in v if x not in stopwords.words('romanian')]
			#  Russian
			elif stoplang == 'ru':
				self.documents[k] = [x for x in v if x not in stopwords.words('russian')]
			#  Turkish
			elif stoplang == 'tr':
				self.documents[k] = [x for x in v if x not in stopwords.words('turkish')]
			#  Swedish
			elif stoplang == 'sv':
				self.documents[k] = [x for x in v if x not in stopwords.words('swedish')]
			#  Chinese
			elif stoplang == 'zh':
				self.documents[k] = [x for x in v]
			#  English is the default
			else:
				self.documents[k] = [x for x in v if x not in stopwords.words('english')]

			docsCtr += 1

			if self.verbose:
				sys.stdout.write('Pulling stopwords: ' + \
					             str(int(float(docsCtr) / float(docsTotal) * 100)) + '%' + "\r")
				sys.stdout.flush()

		if self.verbose:
			print("")

		return

	#  Only has an effect if the Lemmatizer has already been initialized.
	def lemmatizeCorpus(self):
		if self.lemma is not None:
			if type(self.lemma).__name__ == 'SnowballStemmer':
				docsCtr = 0
				docsTotal = len(self.documents.items())

				if self.verbose:
					print("")
					sys.stdout.write('Lemmatizing corpus with Snowball: 0%' + "\r")
					sys.stdout.flush()

				for k, v in self.documents.items():
					self.documents[k] = [self.lemma.stem(x) for x in v]
					docsCtr += 1

					if self.verbose:
						sys.stdout.write('Lemmatizing corpus with Snowball: ' + \
							             str(int(float(docsCtr) / float(docsTotal) * 100)) + '%' + "\r")
						sys.stdout.flush()

				if self.verbose:
					print("")

			elif type(self.lemma).__name__ == 'WordNetLemmatizer':
				if self.lang == "en":
					docsCtr = 0
					docsTotal = len(self.documents.items())

					if self.verbose:
						print("")
						sys.stdout.write('Lemmatizing corpus with WordNet: 0%' + "\r")
						sys.stdout.flush()

					for k, v in self.documents.items():
						self.documents[k] = [self.lemma.lemmatize(x) for x in v]
						docsCtr += 1

						if self.verbose:
							sys.stdout.write('Lemmatizing corpus with WordNet: ' + \
							                 str(int(float(docsCtr) / float(docsTotal) * 100)) + '%' + "\r")
							sys.stdout.flush()

					if self.verbose:
						print("")
				else:
					print("WordNet can only lemmatize in English. Current language is " + self.lang)

		return

	#  Set the language-identification string for this object.
	#  This indicator is used to determine which stopwords to pull out.
	def setLang(self, lang):
		self.lang = lang
		return

	#  Initialize the WordNet Lemmatizer.
	#  This is only useful for English, so do not initialize this object
	#  upon initialization of this class.
	def initWordNetLemma(self):
		self.lemma = WordNetLemmatizer()
		return

	#  Initialize the Snowball Lemmatizer.
	#  This is only useful for English, so do not initialize this object
	#  upon initialization of this class.
	def initSnowballLemma(self):
		if self.lang == 'da':		#  Danish
			self.lemma = SnowballStemmer("danish")
		elif self.lang == 'nl':		#  Dutch
			self.lemma = SnowballStemmer("dutch")
		elif self.lang == 'fi':		#  Finnish
			self.lemma = SnowballStemmer("finnish")
		elif self.lang == 'fr':		#  French
			self.lemma = SnowballStemmer("french")
		elif self.lang == 'de':		#  German
			self.lemma = SnowballStemmer("german")
		elif self.lang == 'hu':		#  Hungarian
			self.lemma = SnowballStemmer("hungarian")
		elif self.lang == 'it':		#  Italian
			self.lemma = SnowballStemmer("italian")
		elif self.lang == 'no':		#  Norwegian
			self.lemma = SnowballStemmer("norwegian")
									#  Portuguese
		elif self.lang == 'pt' or self.lang == 'pt_BR' or self.lang == 'pt_PT':
			self.lemma = SnowballStemmer("portuguese")
		elif self.lang == 'ro':		#  Romanian
			self.lemma = SnowballStemmer("romanian")
		elif self.lang == 'ru':		#  Russian
			self.lemma = SnowballStemmer("russian")
		elif self.lang == 'es':		#  Spanish
			self.lemma = SnowballStemmer("spanish")
		elif self.lang == 'sv':		#  Swedish
			self.lemma = SnowballStemmer("swedish")
		#  24MAR18: Turkish is advertised on the Snowball site, but it doesn't actually run:
		#           https://pypi.python.org/pypi/snowballstemmer
		elif self.lang == 'tr':		#  Turkish
			self.lemma = SnowballStemmer("turkish")
		else:						#  English as default
			self.lemma = SnowballStemmer("english")
		return

	#  Load the default punctuation list.
	#  This can (and should) be edited according to a given application.
	def loadPunctList(self):
		#  Remove standard (ASCII) punctuation:
		punct = [',', '.', '!', '?', ';', ':', '/', '\\', \
		         '\'', '"', '`', '``', '\'\'', \
		         '(', ')', '[', ']', '{', '}', \
		         '%', '$', '*', '&', '^', '-', '+', '=', \
		       # Full-width (ZH) punctuation:
		       # colon       semi-     comma     full    exclaim.  question    left     right    ideographic
		       #             colon               stop      mark      mark    dbl-quote dbl-quote  comma
		         '\uff1a', '\uff1b', '\uff0c', '\u3002', '\uff01', '\uff1f', '\u201c', '\u201d', '\u3001', \
		       #   left      right     left      right
		       #    <<        >>         <         >
		         '\u300a', '\u300b', '\u3008', '\u3009', \
		       #   full      full
		       #  width (   width )
		         '\uff08', '\uff09']
		return punct
