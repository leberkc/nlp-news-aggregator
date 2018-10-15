import urllib								#  Call Alexa
import MySQLdb								#  Used for DB operations
import re									#  Clean up URLs with Regular Expressions
import time									#  Track how long things take
import calendar								#  Get the sample timestamp
from datetime import datetime
import sys									#  For system output and command line arguments

#  Get Alexa ranks, quietly
#  python alexachron.py n

#  Get Alexa ranks, show your work
#  python alexachron.py y

#  argv[0] = alexachron.py
#  argv[1] = verbosity {y, n}
def main():
	verbose = False							#  False by default
	if len(sys.argv) > 1:					#  Is screen output desired?
		if sys.argv[1].upper()[0] == 'Y':
			verbose = True

	startTime = time.mktime(time.gmtime())	#  Track how long this process takes
	link = MySQLdb.connect('localhost', 'censor', 'blockme', 'corpora')
	cursor = link.cursor(MySQLdb.cursors.DictCursor)

	uniqueDomains = []						#  List of unique sources to Alexa-rank
											#  URLs are more specific than we actually need,
											#  but we must begin by pulling them all.
	query = 'SELECT url FROM articles WHERE 1;'
	cursor.execute(query)
	result = cursor.fetchall()
	for row in result:
		if row['url'] is not None:
			url = row['url'][:]
			if 'http://' in url:			#  Remove "http://" and "https://"
				url = url.replace("http://", "")
			if 'https://' in url:
				url = url.replace("https://", "")
			parse = url.split('/')
			if parse[0][0:4] == 'www.':		#  Remove "www."
				url = parse[0][4:]
			else:
				url = parse[0][:]

			if url not in uniqueDomains:
				uniqueDomains.append(url)
											#  Time stamp of when these ranks were accurate
	sampleTime = calendar.timegm(time.gmtime())

	if verbose:
		print("\n")
		sys.stdout.write('Updating database: 0%' + "\r")
		sys.stdout.flush()

	i = 0
	for url in uniqueDomains:
		xml = urllib.urlopen('http://data.alexa.com/data?cli=10&dat=s&url=' + url).read()
		try: rank = int(re.search(r'<POPULARITY[^>]*TEXT="(\d+)"', xml).groups()[0])
		except: rank = None

		if rank is not None:
			query  = 'INSERT INTO alexa_rank(src, sampled, rank)'
			query += ' VALUES("' + url + '", ' + str(sampleTime) + ', ' + str(rank) +' );'
			cursor.execute(query)
			link.commit()

		if verbose:
			sys.stdout.write('Updating database: ' + \
			                 str(int(float(i + 1) / float(len(uniqueDomains)) * 100)) + '%' + "\r")
			sys.stdout.flush()

		i += 1

	if verbose:
		print("\n")

	stopTime = time.mktime(time.gmtime())	#  Stop the timer

	query = 'INSERT INTO performance_metrics(process, parameter, date_started, sec)'
	query += ' VALUES("alexa ranked", ' + str(len(uniqueDomains)) + ', "'
	query +=   datetime.fromtimestamp(int(startTime)).strftime('%Y-%m-%d %H:%M:%S') + '", '
	query +=   str(stopTime - startTime) + ');'
	cursor.execute(query)
	link.commit()

	cursor.close()
	link.close()							#  Close link to DB
	if verbose:
		print('Done')

if __name__ == '__main__':
	main()