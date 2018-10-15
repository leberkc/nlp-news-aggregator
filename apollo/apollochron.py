import sys
from apollo import Apollo

#  Compute Collective-Action-Potential
#  for all documents in English,
#  and show your work
#  python apollochron.py en y

#  argv[0] = apollochron.py
#  argv[1] = language filter: * means any language
#  argv[2] = verbosity

def main():
	lang = 'en'
	verbosity = False

	if len(sys.argv) > 1:
		lang = sys.argv[1]					#  Language indicated

	if len(sys.argv) > 2:
		if sys.argv[2].upper()[0] == 'Y':	#  Verbosity indicated
			verbosity = True

	a = Apollo()
	a.verbose = verbosity
	a.collectiveActionPotential(10, 0.7)

	return

if __name__ == '__main__':
	main()