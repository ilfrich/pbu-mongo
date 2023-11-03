from setuptools import setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(name="pbumongo",
      version="1.2.0",
      description="Basic MongoDB wrapper for object-oriented collection handling",
      long_description=long_description,
      long_description_content_type="text/markdown",
      url="https://github.com/ilfrich/pbu-mongo",
      author="Peter Ilfrich",
      author_email="das-peter@gmx.de",
      license="Apache-2.0",
      packages=[
          "pbumongo"
      ],
      install_requires=[
          "pymongo==3.11.2",
          "pbu>=1.1.5"
      ],
      tests_require=[
          "pytest",
      ],
      zip_safe=False)
