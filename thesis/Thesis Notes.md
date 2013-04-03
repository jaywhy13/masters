# Research Notes 

### Search Algorithm
* Parse and identify names first (start with larger weighted categories first)
* Score each reference by:
 - Proximity to other locations, std deviation from the centroid 
 - Number of uses in the same text 
 - How common the name is
 - Place name indicators (title case,
 - Calculate the centroid of all places
 - Remove points for references more than 2 SD from the centroid
 - Recalculate the centroid of all places
 - Throw NLTK's classification into the loop
 - Comparison of how names are used
 
### Weightings 
#### Parish
* Initial  +30 points
#### Community
* Initial +10 points
* Parish in article  +15 points

#### General
* Common -10 points
* Not lower cased +5 points
* Not followed/preceded by NP +15 points
* Within 1 Stan Dev of centroid and > 1 references +10 points
* NLTK NE Tag +10 points

#### Todo:
 - Fix find_references method... needs to take a list (DONE)
 - Add a get_sentences method (DONE)
 - Add sentence, sentence_number and position_in_sentence to reference. (DONE)
 - Add a reference.sentence, reference.get_surronding_words, reference.get_pos_tagged (DONE)
 - Use NLTK to examine POS of different types of occurrences 
 - Build a geo stop word list by virtue of occurrence (DONE)
 - Add method to get random x articles that haven't been reviewed 
 - Find references to Jamaica in the articles reviewed thus far 
 - Vary pass mark
 - Find pass mark necessary to achieve F-measure of 0.8. 
 - Vary weightings 
 - Add a review_references page to check over references .... or just add Admin link
 - Review references like "Kingston police division", "Kingston Police Division" and "Arnette Gardens Football team"
 - Also review joined references like "Kingston and St Andrew"
 - Find out how to review tagged locations in NLTK corpus
 - Find popular surnames 
 - Get NLTK classification of word by sentence, index

#### Variables to vary:
* Centroid deviation deduction
* Centroid deviation 

# NLTK Notes
* nltk.word_tokenize(str) - tokenize words...
* Use str.splitlines() to parse Article body into sentences

### Popular name sources
* http://www.my-island-jamaica.com/jamaican_surnames.html
* http://www.babynames.org.uk/jamaican-boy-baby-names.htm
* http://www.studentsoftheworld.info/penpals/stats.php3?Pays=JAM
* http://parentingliteracy.com/baby-names/66-baby-names-by-nationality/130-popular-jamaican-baby-names
* http://staceymarierobinson.blogspot.com/2009/09/top-100-jamaican-names.html
* http://www.englishclub.com/vocabulary/common-words-5000.htm