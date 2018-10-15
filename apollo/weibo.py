# -*- coding: utf-8 -*-

import re									#  For find-replace regular expressions
import sys									#  For overwriting output to the screen (verbose mode)
import bs4									#  Used to find() the bits we want
from bs4 import BeautifulSoup
											#  Weibo is tricky: we'll need to wait for page loads and feed
from selenium import webdriver				#  it account credentials before it coughs up anything for us
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import WebDriverException
											#  Needed to specify running headless
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.keys import Keys

from guess_language import *				#  Pretty lame trigram detector... but it's free
import MySQLdb								#  Used for DB operations
import datetime								#  Used for time stamping our retrievals
from datetime import datetime				#  Used for time stamping our retrievals
import time									#  Track how long things take

#  The job of this class is to periodically grab a bunch of posts from Weibo.com,
#  parse them and save them to the database. Another routine will perform analysis, which takes
#  a bit more time. The idea here is to constantly be retrieving as much content as possible.
class WeiboFetcher:
	#  fetcher = WeiboFetcher('localhost', 'censor', 'blockme', 'corpora')
	def __init__(self, dbHost=None, dbUser=None, dbPword=None, dbTable=None):
		self.posts = []						#  List of Weibo posts, stored here as dictionary objects:
											#  One {} per post:
											#  ['author'] = Weibo user name
											#  ['content-text'] = DB-safe text of post
											#  ['content-media'] = Markup for associated media (if applicable)
											#  ['pub-date'] = Date time of publication
											#  ['date-retrieved'] = The date we collected this post
		self.weiboUName = None				#  The username we give to Weibo
		self.weiboPWord = None				#  The password we give to Weibo

		self.link = None					#  MySQL link
		self.dbHost = dbHost				#  String indicating database host
		self.dbUser = dbUser				#  String indicating database user
		self.dbPword = dbPword				#  String indicating database user's password
		self.dbTable = dbTable				#  String indicating database table

		self.browser = None					#  Must first be initialized and can be initialized with whichever
											#  settings you want. For instance, a user profile with ad-blocking
											#  will enjoy improved load-times, but might also make Weibo impossible
											#  since Weibo requires trackers.
		self.currentPage = None				#  Various options exist once we've established our puppet browser, so
											#  save the most recent page successfully loaded and pass control to
											#  desired class methods.

		self.removeLB = True				#  Whether we remove line breaks
		self.replaceSpecial = True			#  Whether to use the replacement dictionary to swap out special chars
		self.replaceDict = self.initReplace()
		self.verbose = False				#  Whether to print progress to screen (sometimes spits up funky chars)
		self.debugFile = False				#  Whether to output queries to a debug file

		self.startTime = None				#  Time this routine
		self.stopTime = None

		return

	#  Weibo does not reveal much of anything without SOME degree of user-participation.
	#  Meaning we must log in before we can search or scrape.
	#  This class will take the procedure a step at a time: first thing is to log in.
	#  Login may be thwarted if the page loads too slowly or returns an error.
	#  This method returns False if something went wrong, and True if we successfully logged into Weibo.
	def login(self, uname=None, pword=None):
		if uname is None:
			uname = self.weiboUName
		if pword is None:
			pword = self.weiboPWord

		if self.browser is not None:

			url = "https://weibo.com/login.php"
			self.browser.get(url)
			try:
				self.currentPage = WebDriverWait(self.browser, timeout=120).until(lambda x: x.find_element_by_id('loginname'))
			except TimeoutException:
				if self.verbose:
					print('Connection to Weibo timed out.')
				self.currentPage = None
			except WebDriverException:
				if self.verbose:
					print('A web driver exception occurred')
				self.currentPage = None

			if self.currentPage is not None:
				if self.verbose:
					print('Successfully connected to Weibo!')

				usernameField = self.browser.find_element_by_id('loginname')
				passwordField = self.browser.find_element_by_name('password')
				loginButton = self.browser.find_element_by_xpath('//a[@node-type="submitBtn"]')

				if self.verbose:
					if usernameField is not None:
						print('\tSelenium located username input field')
					if passwordField is not None:
						print('\tSelenium located password input field')
					if loginButton is not None:
						print('\tSelenium located login button')

				if usernameField is not None and passwordField is not None and loginButton is not None:
					if uname is not None and pword is not None:
						usernameField.send_keys(uname)
						passwordField.send_keys(pword)
						#loginButton.send_keys(Keys.ENTER)
						loginButton.click()

						try:
							#page = WebDriverWait(self.browser, timeout=120).until(lambda x: x.find_element_by_id('loginname'))
							self.currentPage = WebDriverWait(self.browser, timeout=120)
						except TimeoutException:
							if self.verbose:
								print('Login to Weibo timed out.')
							self.currentPage = None
						except WebDriverException:
							if self.verbose:
								print('A web driver exception occurred')
							self.currentPage = None

						if self.currentPage is not None:
							if self.verbose:
								print('Submitted Weibo credentials and received a page!')
							return True

					elif self.verbose:
						print('No username and/or password provided for Weibo')
				elif self.verbose:
					print('Unable to find login fields on retrieved page')

		elif self.verbose:
			print('You must initialize your web browser before you can log in.')

		return False

	#  Method assumes you've logged in successfully first.
	#  Weibo offers some initial posts from established contributors (mostly advertisers) when users log in.
	#  These *may* be worth saving, but more "organic" content will only be found by first searching a term.
	#  All this method does is collect whatever appeared on the home page.
	def fetchDefault(self):
		#  Create list of all posts retrieved
		allPosts = []

		if self.browser is not None:
			if self.currentPage is not None:
				soup = BeautifulSoup(self.currentPage, 'html.parser')

				#  Get all ready-presented posts
				landingpageRecommended = soup.findAll('div', attrs={'class':['WB_cardwrap', 'WB_feed_type']})
				for landpageRec in landingpageRecommended:
					#  If we receive more than one post in a batch, then they reply to each other.
					#  Link them before adding them to the entire haul.
					batch = self.processPost(landpageRec)
					if len(batch) > 1:
						#  Initialize a link-counter
						linkctr = 0
						for i in range(0, len(batch)):
							if i < len(batch) - 1:
								batch[i]['replies_to'] = linkctr + 1
							linkctr += 1
					#  Add all posts to collection
					allPosts += batch

			elif self.verbose:
				print('Browser initialized, but no page has been loaded.')
		elif self.verbose:
			print('You must initialize your web browser and log in before you can collect content.')

		return allPosts

	#  Method assumes you've logged in successfully first.
	#  This method plugs the searchTerm into Weibo's topic search field and scrapes the returned posts.
	#  As above in fetchDefault(), if a post is a reply to a post, then we save both and link them.
	def fetchFromSearch(self, searchTerm, uname=None, pword=None):
		if uname is None:
			uname = self.weiboUName
		if pword is None:
			pword = self.weiboPWord

		#  Create list of all posts retrieved
		allPosts = []

		if self.browser is not None:
			if self.currentPage is not None:
				searchField = self.browser.find_element_by_xpath('//input[@node-type="simpleSearch"]')
				if self.verbose:
					if searchField is not None:
						print('\tSelenium located search field')

				if searchField is not None:
						searchField.send_keys(searchTerm)
						searchField.send_keys(Keys.ENTER)

						try:
							self.currentPage = WebDriverWait(self.browser, timeout=120)
						except TimeoutException:
							if self.verbose:
								print('Search timed out.')
							self.currentPage = None
						except WebDriverException:
							if self.verbose:
								print('A web driver exception occurred')
							self.currentPage = None

						if self.currentPage is not None:
							if self.verbose:
								print('Submitted search and received results!')

							soup = BeautifulSoup(self.currentPage, 'html.parser')

							#  Get all ready-presented posts
							results = soup.findAll('div', attrs={'class':['WB_cardwrap', 'WB_feed_type']})
							for result in results:
								batch = self.processPost(result)

								#  First order of business: mark these posts as resulting from a specific search
								for post in batch:
									post['searched'] = searchTerm

								#  If we receive more than one post in a batch, then they reply to each other.
								#  Link them before adding them to the entire haul.
								if len(batch) > 1:
									#  Initialize a link-counter
									linkctr = 0
									for i in range(0, len(batch)):
										if i < len(batch) - 1:
											batch[i]['replies_to'] = linkctr + 1
										linkctr += 1
								#  Add all posts to collection
								allPosts += batch

			elif self.verbose:
				print('Browser initialized, but no page has been loaded.')
		elif self.verbose:
			print('You must initialize your web browser and log in before you can collect content.')

		return allPosts

	#  Builds a list of dictionaries, one for each post.
	#  If a post contains another post, then they are adjacent in the list:
	#  [ {#0 points to #1}, {#1 points to #2}, ..., {#n points to #n+1} ]
	def processPost(self, post):
		#  Dictionary holding post data
		ret = {}
		#  Collection of all posts found
		coll = []

		#  Get the author's username ('nick-name') and credentials.
		#  The credentials are the icons immediately to the right of the nick-name.
		#  These tell us how established a cooperator this writer is.
		data = post.find('div', attrs={'class':['WB_info']})
		aTags = data.findAll('a')
		for a in range(0, len(aTags)):
			if a == 0:
				ret['author_name'] = aTags[a]['nick-name']
				ret['author_creds'] = []
				#print aTags[a]['nick-name']
			else:
				icon = aTags[a].find(attrs={'class':['W_icon']})
				#  icon['class'][0] is always W_icon
				ret['author_creds'].append( icon['class'][1] )
				#print icon['class'][1]

		#  Get the UNIX timestamp of this post's publication on Weibo
		data = post.find('div', attrs={'class':['WB_from']})
		aTags = data.findAll('a')
		if len(aTags) > 0 and aTags[0].has_attr('date'):
			ret['pub_date'] = aTags[0]['date']
			#print aTags[0]['date']

		#  Get a text-only version of the post
		data = post.find('div', attrs={'class':['WB_text', 'W_f14']})
		ret['text_only_content'] = repr(data.get_text().replace(' ', '').replace('\n', ''))[2:-1]
		#print repr(data.get_text().replace(' ', '').replace('\n', ''))[2:-1]

		#  Stick the dictionary object into a list
		coll.append( ret )

		#  Does this post refer to an included, previous post? RECURSION!
		data = post.findAll('div', attrs={'class':['WB_expand']})
		if len(data) > 0:
			coll += self.processPost( data[0] )

		return coll

	#  Closing the session should hopefully limit suspicion.
	def logout(self):
		if self.browser is not None:
			url = "https://weibo.com/logout.php?backurl=%2F"
			self.browser.get(url)
		return

	def initBrowser(self):
		options = Options()
		#  Tell Selenium not to expect a browser window or display monitor
		options.add_argument("--headless")
		#  Point to Geckodriver
		self.browser = webdriver.Firefox(firefox_options=options, executable_path='/usr/local/bin/geckodriver')
		return

	def setWeiboUserName(self, uname):
		self.weiboUName = uname
		return

	def setWeiboPassword(self, pword):
		self.weiboPWord = pword
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
