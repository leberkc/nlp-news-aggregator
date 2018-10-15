import sys
from freeweibo import FreeWeiboFetcher

#  Scrape posts and show your work
#  python freeweibochron.py y

#  argv[0] = freeweibochron.py
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

	fetcher = FreeWeiboFetcher('localhost', 'censor', 'blockme', 'corpora')
	fetcher.verbose = verbosity
	fetcher.debugFile = debugOutput
	fetcher.openDB()
	fetcher.fetch()
	fetcher.save()
	fetcher.closeDB()

if __name__ == '__main__':
	main()