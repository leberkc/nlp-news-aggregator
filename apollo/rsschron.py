import sys
from rss import FeedFetcher

#  Scrape feeds
#  and show your work
#  python rsschron.py y

#  argv[0] = rsschron.py
#  argv[1] = verbosity {Y/N}
#  argv[2] = debug output to file {Y/N}
def main():
	verbosity = False
	debugOutput = False

	if len(sys.argv) > 1:
		if sys.argv[1].upper()[0] == 'Y':
			verbosity = True

	if len(sys.argv) > 2:
		if sys.argv[2].upper()[0] == 'Y':
			debugOutput = True

	fetcher = FeedFetcher('localhost', 'censor', 'blockme', 'corpora')
	fetcher.verbose = verbosity
	fetcher.debugFile = debugOutput
	fetcher.openDB()
	fetcher.getFeeds()
	fetcher.save(fetcher.fetch())
	fetcher.closeDB()

if __name__ == '__main__':
	main()