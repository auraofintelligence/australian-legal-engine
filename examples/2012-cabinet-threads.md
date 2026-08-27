# What the 2012 cabinet points at

One person spent the summer of 2012 to 2013 collecting every law that
touched their own life: 61 documents, saved between November 2012 and
November 2014. The story is at
https://auraofintelligence.github.io/australian-law-2012-lukes-relevance/

This file is what happens when the engine reads that collection for the
references its acts make to each other and to acts that are not in it.

- 48 acts parsed
- 101,371 provisions indexed
- 21,346 threads found

Act names and counts only. No legislative text is reproduced here.

## The gap the law names for itself

The acts in the collection point at these acts, which the collection
does not contain. This is a reading list nobody had to guess at.

| References | Act | First seen at |
| ---: | --- | --- |
| 1365 | Income Tax Assessment Act 1997 | A New Tax System (Pay As You Go) Act 1999 Schedule 1, s 11(2) |
| 310 | Acts Interpretation Act 1901 | Australian Acts Interpretation Amendment Act 2011 Schedule 2, s 234(d) |
| 264 | Income Tax Assessment Act 1936 | A New Tax System (Pay As You Go) Act 1999 Schedule 1, s 11(3)(b) |
| 223 | Crimes Act 1914 | A New Tax System (Pay As You Go) Act 1999 Schedule 1, s 11(2) |
| 146 | Legislative Instruments Act 2003 | Australian Acts Interpretation Amendment Act 2011 Schedule 1, s 1A(1) |
| 68 | Administrative Appeals Tribunal Act 1975 | Anti-Money Laundering and Counter-Terrorism Financing Act 2006 s 75S(2) |
| 61 | Public Service Act 1999 | Australian Acts Interpretation Amendment Act 2011 Schedule 1, s 2B(d) |
| 60 | Student Assistance Act 1973 | Social Security Act 1991 Schedule 1A, s 5F(a) |
| 56 | Customs Act 1901 | Anti-Money Laundering and Counter-Terrorism Financing Act 2006 s 8(b) |
| 52 | Traffic Act 1949 | Transport Operations (Road Use Management) Act 1995 s 185(4)(b) |
| 51 | Family Law Act 1975 | Corporations Act 2001 s 5I(4)(b) |
| 46 | First Home Saver Accounts Act 2008 | Anti-Money Laundering and Counter-Terrorism Financing Act 2006 s 8(a) |
| 42 | Fringe Benefits Tax Assessment Act 1986 | A New Tax System (Pay As You Go) Act 1999 Schedule 1, s 11(2) |
| 41 | State Penalties Enforcement Act 1999 | Electoral Act 1992 s 135(2) |
| 39 | Australian Prudential Regulation Authority Act 1998 | Banking Act 1959 s 2(1) |
| 37 | Farm Household Support Act 1992 | Social Security Act 1991 Schedule 1A, s 19(d) |
| 36 | Financial Services Reform Act 2001 | Corporations Act 2001 s 20(1)(d) |
| 35 | Retirement Savings Accounts Act 1997 | Anti-Money Laundering and Counter-Terrorism Financing Act 2006 s 8(b) |
| 33 | Part VIIIB of the Family Law Act 1975 | Social Security Act 1991 Schedule 1A, s 9A(2)(iva) |
| 31 | Part III of the Income Tax Assessment Act 1936 | A New Tax System (Pay As You Go) Act 1999 Schedule 1, s 11(6)(b) |
| 30 | Bankruptcy Act 1966 | Corporations Act 2001 s 5I(4)(a) |
| 30 | Youth Justice Act 1992 | Police Powers and Responsibilities Act 2000 s 84(1)(b) |
| 30 | Crime and Misconduct Act 2001 | Police Powers and Responsibilities Act 2000 Schedule 3, s 230(2) |
| 29 | Migration Act 1958 | Anti-Money Laundering and Counter-Terrorism Financing Act 2006 s 31(b) |
| 27 | Transport Infrastructure Act 1994 | Transport Operations (Passenger Transport) Act 1994 s 104(3)(b) |

## What the engine could not tell you

The Income Tax Assessment Act 1997 sits at the top by a wide margin, and
it is worth being precise about what that does and does not mean.

The count is a fact about the text: acts in this collection refer to that
act 1,365 times. Whether it belonged in the collection is a different
question, and the engine has no way to reach it.

Here the answer is no. The Assessment Act says what is taxable: income
from investments, capital gains, deductions against assets. The person who
built this collection had no assets and no investments, so none of it
applied to him. What did apply is the other half of tax law, and that is
what he took: the Taxation Administration Act 1953 in both volumes, the
pay as you go act, the tax file number application, and the small supplier
form that started the whole read. How tax leaves a wage, and how the office
that takes it must behave.

So read this list as what the law leans on, not as a list of mistakes. A
machine can count references. It cannot know your life, and the count
settles nothing on its own.

## Which act leans on which

| References | From | To |
| ---: | --- | --- |
| 1051 | Taxation Administration Act 1953 | Income Tax Assessment Act 1997 |
| 178 | A New Tax System (Pay As You Go) Act 1999 | Income Tax Assessment Act 1997 |
| 146 | Taxation Administration Act 1953 | Income Tax Assessment Act 1936 |
| 114 | Australian Acts Interpretation Amendment Act 2011 | Acts Interpretation Act 1901 |
| 62 | Personal Property Securities (Consequential Amendments) Act 2009 | Personal Property Securities Act 2009 |
| 61 | Social Security Act 1991 | Income Tax Assessment Act 1997 |
| 60 | Banking Act 1959 | Crimes Act 1914 |
| 58 | Taxation Administration Act 1953 | Crimes Act 1914 |
| 56 | A New Tax System (Pay As You Go) Act 1999 | Income Tax Assessment Act 1936 |
| 55 | Social Security Act 1991 | Student Assistance Act 1973 |
| 52 | Transport Operations (Road Use Management) Act 1995 | Traffic Act 1949 |
| 51 | Corporations Act 2001 | Personal Property Securities Act 2009 |
| 51 | Taxation Administration Act 1953 | Corporations Act 2001 |
| 49 | Banking Act 1959 | Corporations Act 2001 |
| 42 | Life Insurance Act 1995 | Corporations Act 2001 |
| 39 | A New Tax System (Pay As You Go) Act 1999 | Taxation Administration Act 1953 |
| 35 | Corporations Act 2001 | Financial Services Reform Act 2001 |
| 35 | Social Security Act 1991 | Farm Household Support Act 1992 |
| 33 | Taxation Administration Act 1953 | Acts Interpretation Act 1901 |
| 30 | Therapeutic Goods Act 1989 | Customs Act 1901 |

## Reproducing this

```bash
python -m engine index "path/to/your/acts/*.pdf" --out data/index.json
python -m engine threads
```

Every thread keeps the words it came from, so any line above can be
checked against the provision that produced it.
