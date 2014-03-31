# sg -- stupid git

Stupid git is a very simple "implementation" of git in Python. It's the result of me trying to understand how git actually works. It's actually quite clever as it relies on a few core 'principles': immutable objects (blobs, commits, trees, tags) and mutable references (`HEAD`s, branches, tags).

If you only ever used the porcelain git commands (`commit`, `add`, etc) I recommend reading more about the internals, also known as plumbing commands (e.g. `hash-object`, `write-tree`, etc). The references I used to write `sg` are listed at the bottom of this file.

`sg` only implements a few porcelain methods, but that's enough to let you create your own commits, for instance look at example session a bit below. This **is** full of bugs and is not meant to be used for managing real repository, that being said it implements enough to understand how the basic git features work (and it would be fairly easy to add new functions, such as `branch`, `add` or `commit` for instance. None of the remote features are implemented.

It runs on Python `3.4+` w/o dependencies.

## Example

     ✓ ~/sg/test $ alias sg=../sg.py
     ✓ ~/sg/test $ sg init
     ✓ ~/sg/test (master) $ echo a > a
     ✓ ~/sg/test (master) $ echo b > b
     ✓ ~/sg/test (master) $ sg hash-object -w a b
    78981922613b2afb6025042ff6bd878ac1994e85
    61780798228d17af2d34fce4cfbdf35556832472
     ✓ ~/sg/test (master) $ sg update-index --add a
     ✓ ~/sg/test (master) $ sg write-tree
    8e47fca129517ba3cd6a0650b462128386c8e7da
     ✓ ~/sg/test (master) $ echo 'First commit w/o using git CLI!' | sg commit-tree 8e47fca129517ba3cd6a0650b462128386c8e7da
    4640cf89181aa094594dfa8ee4f079785d6213f4
     ✓ ~/sg/test (master) $ sg update-index --add b
     ✓ ~/sg/test (master) $ sg write-tree
    97a96a08809ff9c82950792c011f1eff23af1af0
     ✓ ~/sg/test (master) $ echo 'Commit with a parent!' | sg commit-tree -p 4640cf89181aa094594dfa8ee4f079785d6213f4 97a96a08809ff9c82950792c011f1eff23af1af0
    2715b676baaf5711a973aa3d0981bce7d491a3e7
     ✓ ~/sg/test (master) $ sg update-ref HEAD 2715b676baaf5711a973aa3d0981bce7d491a3e7
     ✓ ~/sg/test (master) $ git log --graph --format=oneline
    * 2715b676baaf5711a973aa3d0981bce7d491a3e7 Commit with a parent!
    * 4640cf89181aa094594dfa8ee4f079785d6213f4 First commit w/o using git CLI!

## References

* [Git Book / Git Internals](http://git-scm.com/book/en/Git-Internals), Scott Chacon
* [Git Internals](https://github.com/pluralsight/git-internals-pdf), Scott Chacon
* [Git from the bottom up](http://ftp.newartisans.com/pub/git.from.bottom.up.pdf), John Wiegley
* [gitcore-tutorial(7)](https://www.kernel.org/pub/software/scm/git/docs/gitcore-tutorial.html)
* [gitrepository-layout(5)](https://www.kernel.org/pub/software/scm/git/docs/gitrepository-layout.html)
* [index-format.txt](https://www.kernel.org/pub/software/scm/git/docs/technical/index-format.txt)
