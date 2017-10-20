# -*- coding: utf-8 -*-
# define our feeds
#import codecs, sqlite3
import codecs
import time
import urllib, sys, re
from datetime import datetime

starTime = datetime.now()
start_time = time.time()
# Open database connection

import MySQLdb
db = MySQLdb.connect("localhost","censor","blockme","news" )
# prepare a cursor object using cursor() method
cursor = db.cursor()



#conn = sqlite3.connect('database.db')
#c = conn.cursor()
#c.execute('CREATE TABLE IF NOT EXISTS articles(id INTEGER, cluster_id INTEGER, article_title TEXT, url TEXT, rank TEXT)')

feeds = [
#China News
    'http://www.chinadaily.com.cn/rss/china_rss.xml',
#Bizchina News
    'http://www.chinadaily.com.cn/rss/bizchina_rss.xml',
#World News
    'http://www.chinadaily.com.cn/rss/world_rss.xml',
#Opinion News
    'http://www.chinadaily.com.cn/rss/opinion_rss.xml',
#Sports News
#    'http://www.chinadaily.com.cn/rss/sports_rss.xml',
#Entertainment News
#    'http://www.chinadaily.com.cn/rss/entertainment_rss.xml',
#Life News
#    'http://www.chinadaily.com.cn/rss/lifestyle_rss.xml',
#Photo News
#    'http://www.chinadaily.com.cn/rss/photo_rss.xml',
#Video News
#    'http://www.chinadaily.com.cn/rss/video_rss.xml',
#China Daily News
    'http://www.chinadaily.com.cn/rss/cndy_rss.xml',
#HK Edition News
#    'http://www.chinadaily.com.cn/rss/hk_rss.xml',
#China Daily USA News
#    'http://usa.chinadaily.com.cn/usa_kindle.xml',
#China Daily European Weekly News
    'http://europe.chinadaily.com.cn/euweekly_rss.xml',
###############################################################
#Added on 10/16/2017
#China
    'http://en.people.cn/rss/China.xml',

#Business
    'http://en.people.cn/rss/Business.xml',

#Opinion
    'http://en.people.cn/rss/Opinion.xml',

#Dmestic News	
    'http://www.people.com.cn/rss/politics.xml',

#International News	
    'http://www.people.com.cn/rss/world.xml',

#Economic news	
    'http://www.people.com.cn/rss/finance.xml',
		
#Taiwan news	
    'http://www.people.com.cn/rss/haixia.xml',

#Education news	
    'http://www.people.com.cn/rss/edu.xml',
#
#Chinese news	
    'http://www.people.com.cn/rss/opml.xml',
###############################################################


#BBC China News
#    'http://newsrss.bbc.co.uk/rss/chinese/simp/news/rss.xml',

#     'http://english.cntv.cn/service/rss/0/index.xml',
#     'http://www.chinapost.com.tw/rss/front.xml'

#----------------------------------------------------------
#    'http://feeds.bbci.co.uk/news/world/rss.xml',
#    'http://www.cbn.com/cbnnews/world/feed/',
#    'http://news.yahoo.com/rss/',
#    'http://www.cbn.com/cbnnews/us/feed/',
#    'http://feeds.reuters.com/reuters/technologyNews',
#    'http://feeds.bbci.co.uk/news/rss.xml',
#    'http://feeds.reuters.com/Reuters/worldNews'
]




# parse the feeds into a set of words per document
import urllib, bs4
import feedparser
import nltk
from bs4 import BeautifulSoup
corpus = []
titles=[]
links=[]
ct = -1
s = ''
m = ''
for feed in feeds:
    d = feedparser.parse(feed)
#    url = d.entries[0].media_content[0]['url'] 

    for e in d['entries']:
       
#        url = e[1]['url'] 
#        url = BeautifulSoup(e['url']) 
        words = nltk.wordpunct_tokenize(BeautifulSoup(e['summary'].encode('utf-8'), 'html.parser').get_text())
        words.extend(nltk.wordpunct_tokenize(e['title']))
        lowerwords=[x.lower() for x in words if len(x) > 1]
        ct += 1
        print(ct, "TITLE",e['title'])
#        print  e.link 
        corpus.append(lowerwords)
        titles.append(e['title'])
        print(e.keys())
#        links.append(e.link)
        if 'link' in e:
               links.append(e.link)
        else:
#               links.append("No Link Present") 
               links.append("0") 
                   


# tf-idf implementation
# from http://timtrueman.com/a-quick-foray-into-linear-algebra-and-python-tf-idf/

import math
from operator import itemgetter
def freq(word, document): return document.count(word)
def wordCount(document): return len(document)
def numDocsContaining(word,documentList):
  count = 0
  for document in documentList:
    if freq(word,document) > 0:
      count += 1
  return count
def tf(word, document): return (freq(word,document) / float(wordCount(document)))
def idf(word, documentList): return math.log(len(documentList) / numDocsContaining(word,documentList))
def tfidf(word, document, documentList): return (tf(word,document) * idf(word,documentList))


# extract top keywords from each doc.
# This defines features of our common feature vector

import operator
def top_keywords(n,doc,corpus):
    d = {}
    for word in set(doc):
        d[word] = tfidf(word,doc,corpus)
    sorted_d = sorted(d.items(), key=operator.itemgetter(1))
    sorted_d.reverse()
    return [w[0] for w in sorted_d[:n]]   

key_word_list=set()
nkeywords=4
[[key_word_list.add(x) for x in top_keywords(nkeywords,doc,corpus)] for doc in corpus]
   
ct=-1
for doc in corpus:
    ct+=1
    print(ct,"KEYWORDS"," ".join(top_keywords(nkeywords,doc,corpus)))


# turn each doc into a feature vector using TF-IDF score

feature_vectors=[]
n=len(corpus)

for document in corpus:
    vec=[]
    [vec.append(tfidf(word, document, corpus) if word in document else 0) for word in key_word_list]
    feature_vectors.append(vec)

#print feature_vectors[1]

# now turn that into symmatrix matrix of 
# cosine similarities

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
#from scipy.spatial.distance import cdist
from scipy import spatial, sparse
#mat = numpy.empty((n, n))
#mat = np.empty((n, n))
mat = np.zeros((n, n))
for i in xrange(0,n):
    for j in xrange(0,n):
#     mat = np.concatenate(feature_vectors[i],axis=0)
         mat[i][j] = feature_vectors[i][j]

mat = sparse.csr_matrix(mat)

#       x_csr = sparse.csr_matrix(feature_vectors[i])
#       print x_csr
#       y_csr = sparse.csr_matrix(feature_vectors[j])
#       mat = nltk.cluster.util.cosine_distance(x_csr,y_csr)
#       mat[i][j] = nltk.cluster.util.cosine_distance(x_csr,y_csr)
#       mat[i][j] = nltk.cluster.util.cosine_distance(feature_vectors[i],feature_vectors[j])
#       mat[i][j] = np.sqrt(np.dot(feature_vectors[i], feature_vectors[i])) - (np.dot(feature_vectors[i], feature_vectors[j]) + np.dot(feature_vectors[i], feature_vectors[j])) + np.dot(feature_vectors[j], feature_vectors[j])
#        print(feature_vectors[i])
#       mat[i][j] = cdist(feature_vectors[i], feature_vectors[j], 'euclidean')
#        mat[i][j] = 1 - spatial.distance.cosine(feature_vectors[i],feature_vectors[j]) 
# now hierarchically cluster mat
mat = cosine_similarity(mat)
print("--- %s seconds ---" % (time.time() - start_time))

from hcluster import linkage, dendrogram
t = 0.8
Z = linkage(mat, 'single')
#dendrogram(Z, color_threshold = t)

import pylab
#pylab.savefig( "hcluster.png" ,dpi=800)


# extract our clusters

def extract_clusters(Z,threshold,n):
   clusters={}
   ct=n
   for row in Z:
      if row[2] < threshold:
          n1=int(row[0])
          n2=int(row[1])

          if n1 >= n:
             l1=clusters[n1] 
             del(clusters[n1]) 
          else:
             l1= [n1]
      
          if n2 >= n:
             l2=clusters[n2] 
             del(clusters[n2]) 
          else:
             l2= [n2]    
          l1.extend(l2)  
          clusters[ct] = l1
          ct += 1
      else:
          return clusters

clusters = extract_clusters(Z,t,n)
 
#for key in clusters:
   #print "============================================="
for key in clusters:
   print("=============================================")
   for id in clusters[key]:
       print(id,titles[id])
       print(links[id])
#       if (links[id]=="0"):
#           rank="0"
#       else:
       xml = urllib.urlopen('http://data.alexa.com/data?cli=10&dat=s&url='+ links[id]).read()
       try: rank = int(re.search(r'<POPULARITY[^>]*TEXT="(\d+)"', xml).groups()[0])
       except: rank = -1


#           rank = bs4.BeautifulSoup(urllib.urlopen("http://data.alexa.com/data?cli=10&dat=s&url="+ links[id]).read(), "xml").find("REACH")['RANK']
       print(rank)
#       print bs4.BeautifulSoup(urllib.urlopen("http://data.alexa.com/data?cli=10&dat=s&url="+ sys.argv[1]).read(), "xml").find("REACH")['RANK']
#       c.execute("INSERT INTO articles (id, cluster_id, article_title, url, rank) VALUES (?, ?, ?, ?, ?)", (id, key, titles[id].encode('utf8'), links[id].encode('utf8'), rank))


#       cursor.execute("INSERT INTO articles (id, cluster_id, article_title, url, rank, timestamp) VALUES (%s, %s, %s, %s, %s, %s)", (id, key, titles[id].encode('utf8'), links[id].encode('utf8'), rank, timestamp))
       cursor.execute("INSERT INTO articles (id, cluster_id, article_title, url, rank) VALUES (%s, %s, %s, %s, %s)", (id, key, titles[id].encode('utf8'), links[id].encode('utf8'), rank ))
       db.commit()
#       connection.commit()

#!/usr/bin/env python
# Google Pagerank Algo

# Settings
#    print clusters[key]

#if __name__ == "__main__" :
#    print GetPageRank("http://schurpf.com/")
#    print" The topmost article:"
#for id in clusters[key]:
#    print id,titles[id]
db.close()
#connection.close()
print datetime.now() - starTime    
