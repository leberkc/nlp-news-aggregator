import sys
from bagger import ArticleBagger

#  Bag 10 records,
#  with confidence at least 0.25,
#  in any language,
#  and show your work
#  python bagchron.py 10 0.25 * y

#  Bag 10 records,
#  with confidence at least 0.25,
#  in English,
#  and show your work
#  python bagchron.py 10 0.25 en y

#  argv[0] = bagchron.py
#  argv[1] = number of records to pull and clean with this process
#  argv[2] = confidence threshold (0.0 to disable confidence)
#  argv[3] = language filter: * means any language
#  argv[4] = verbosity
def main():
	lim = 10								#  Default is 10 articles bagged
	confidence = None						#  Default is no confidence requirement
	langFilter = '*'						#  Bag any language by default
	verbosity = False						#  Turn off print-outs by default

	if len(sys.argv) > 1:
		lim = int(sys.argv[1])				#  Limit indicated
		if lim < 1:							#  Must bag at least one record
			lim = 1

	if len(sys.argv) > 2:
		confidence = float(sys.argv[2])		#  Confidence threshold indicated

	if len(sys.argv) > 3:
		langFilter = sys.argv[3]			#  Language filter indicated

	if len(sys.argv) > 4:
		if sys.argv[4].upper()[0] == 'Y':	#  Verbosity indicated
			verbosity = True

	c = ArticleBagger(lim, 'localhost', 'censor', 'blockme', 'corpora')
	c.setLanguage(langFilter)				#  Set language, if we received anything meaningful
	if confidence is not None:				#  Apply confidence
		if confidence <= 0.0:
			c.useConfidence = False
		else:
			c.useConfidence = True
			c.confidence = confidence
	c.verbose = verbosity					#  Apply verbosity

	c.openDB()								#  Run!
	c.batchClean()
	c.batchSave()
	c.closeDB()

if __name__ == '__main__':
	main()