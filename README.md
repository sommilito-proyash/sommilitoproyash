# সম্মিলিত প্রয়াস — Version 3

Version 2-এর উপর ভিত্তি করে এই সংস্করণে যোগ হয়েছে:
- Notice Board; Admin থেকে Add/Delete এবং Highlight/Pinned
- প্রত্যেক সদস্যের পেজে public comment form; Admin comment delete করতে পারবেন
- Admin থেকে নতুন সদস্য Add
- সদস্যকে Delete না করে Removed/Inactive করা; পুরোনো হিসাব অক্ষত থাকে এবং পরে Activate করা যায়
- আগের বছরভিত্তিক হিসাব, Down Payment 1/2, member profile এবং Admin login বজায় আছে

## ডেমো Admin password
`Sommilito@123`

## Run
`pip install -r requirements.txt`

`python app.py`

তারপর `http://127.0.0.1:5000` খুলুন।

### মন্তব্য ব্যবস্থা
সদস্যের বিস্তারিত পেজে নাম দিয়ে মন্তব্য লেখা যায়। এটি এখন public comment form; বাস্তব অনলাইনে ব্যবহারের আগে চাইলে member-specific login যোগ করা উচিত, যাতে শুধু ১৮ জন সদস্য মন্তব্য করতে পারেন।

### নিরাপত্তা
বাস্তব ব্যবহারের আগে `ADMIN_PASSWORD` ও `SECRET_KEY` environment variable দিয়ে শক্তিশালী মান সেট করুন এবং HTTPS hosting ব্যবহার করুন।
