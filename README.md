# decompile.py

This module decompiles Python bytecodes to the source code. This is a preliminary release - look at the code at the bottom of the source to see how it works.

The code can decompile Python 1.5.2 or 2.0 bytecodes, optimized or not, and returns a dictionary mapping line numbers to lines. There's a number of known problems, and probably quite a lot of unknown problems. The known problems include:

1. it does not put global statements in the code.
1. chained assignment does not work (e.g. "a = b = 1"). It gets decompiled to "a = 1; b = 1" which is sometimes OK, and sometimes not (if the RHS has side effects).
1. tuple arguments in function definitions (e.g. "def f(a, (b, c))") get decompiled to equivalent code that uses an invalid identifier. Fixing this by hand should be fairly simple.
1. List comprehensions don't work. This would be really difficult to get right, but it may be possible (the code handles assert, which is kind of tricky in the same way).
1. The import statement "import spam.ham", valid in 2.0, gets decompiled incorrectly as "import spam.ham as spam"
1. The new "print >> file ..." expression will evaluate "file" once for every item in the argument list. 

The code is licensed under the MIT licence, basically allowing you to do almost anything with the code.

Last Updated: 21 January 2005 
